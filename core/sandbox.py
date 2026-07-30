import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
import subprocess
import re
import multiprocessing
import logging
import threading

logger = logging.getLogger(__name__)

try:
    import docker
    import requests
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

MAX_FILE_CHARS = 30000


# --------------------------------------------------------------------------- #
#  Exécution sécurisée de binaires externes (V4.3.0)                           #
# --------------------------------------------------------------------------- #
def resolve_external_binary(name):
    """Résout le chemin ABSOLU d'un binaire externe via le PATH de
    l'APPLICATION (jamais via le répertoire du projet).

    SÉCURITÉ (V4.3.0) : sous Windows, CreateProcess recherche un exécutable
    donné par son seul nom notamment dans le RÉPERTOIRE COURANT. Comme nos
    sous-processus tournent avec cwd = racine du projet, un dépôt hostile
    contenant un 'graphify.exe' ou 'git.bat' à sa racine aurait été exécuté
    au clic sur le bouton correspondant. On résout donc toujours le binaire
    ici (shutil.which sur le PATH du processus de l'application) et on passe
    un CHEMIN ABSOLU à subprocess. Renvoie None si introuvable."""
    return shutil.which(name)


def hardened_subprocess_env(base_env=None):
    """Environnement durci pour les sous-processus lancés avec
    cwd = racine du projet.

    SÉCURITÉ (V4.3.0) : NoDefaultCurrentDirectoryInExePath empêche, sous
    Windows, la recherche d'exécutables dans le répertoire courant (défense
    en profondeur, en complément des chemins absolus de
    resolve_external_binary)."""
    env = dict(base_env if base_env is not None else os.environ)
    env["NoDefaultCurrentDirectoryInExePath"] = "1"
    return env

def _safe_grep_all_worker(pattern, file_paths, queue, max_matches):
    """Worker de recherche pour isoler l'exécution de la regex dans un processus séparé.
    Prévient le blocage du thread principal en cas de ReDoS."""
    try:
        regex = re.compile(pattern)
        results = []
        for target_path_str, rel_path in file_paths:
            try:
                with open(target_path_str, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line[:2000]):
                            results.append(f"{rel_path}:{i}: {line.strip()}")
                            if len(results) >= max_matches:
                                results.append("... [trop de résultats, recherche tronquée]")
                                queue.put(results)
                                return
            except Exception:
                continue
        queue.put(results)
    except Exception as e:
        queue.put(e)


class FileSandbox:
    _file_lock = threading.Lock()
    # Dossier des rapports d'agents (voir publish_report). Constantes de
    # classe pour être accessibles depuis workers.py sans instance.
    REPORTS_DIRNAME = ".agent_reports"
    REPORTS_HISTORY_KEEP = 10   # versions archivées conservées par agent

    # Fichiers système de L'Atelier IA elle-même : protégés en écriture
    # quand l'outil est pointé sur son propre répertoire source, pour empêcher
    # un agent de réécrire le sandbox et de neutraliser les protections
    # des runs suivants (voir __init__).
    APP_SYSTEM_FILES = {"main.py", "ui.py", "workers.py", "sandbox.py",
                        "llm.py", "utils.py", "nodal_graph.py", "agents.json"}

    def __init__(self, root, checked_paths=None, write_protected_names=None, unchecked_paths=None):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(f"{root} n'est pas un dossier")
        self.use_whitelist = checked_paths is not None
        self.checked_paths = {Path(p).resolve(strict=False) for p in (checked_paths or [])}
        self.unchecked_paths = {Path(p).resolve(strict=False) for p in (unchecked_paths or [])}
        # SÉCURITÉ (V4.0.1) :
        #  - ".agent_recovery.json" rejoint les noms sensibles : il est écrit
        #    et relu directement par le système (workers.py) et empoisonner
        #    son contenu permettrait de corrompre l'état restauré à la
        #    reprise (historiques d'agents, journaux).
        # SÉCURITÉ (V4.4.0) :
        #  - ".agent_last_mission.json" rejoint lui aussi les noms sensibles :
        #    il est relu par l'UI et RÉINJECTÉ comme mission au clic sur 🔄
        #    (Relancer). Un agent qui pouvait l'écrire (même avec le clic de
        #    confirmation habituel) disposait d'un vecteur de persistance
        #    d'injection de prompt identique à celui bouché pour
        #    .agent_recovery.json en V4.0.1.
        self.SENSITIVE_NAMES = {".env", ".git", "__pycache__", ".venv", "node_modules",
                                ".agent_backups", ".agent_recovery.json",
                                ".agent_last_mission.json",
                                "requirements.txt", "package.json"}
        # Fichiers lisibles mais PROTÉGÉS EN ÉCRITURE pour les agents.
        # Sert notamment à empêcher un agent (ou une injection de prompt dans
        # le dépôt) de modifier la mémoire persistante réinjectée à chaque
        # mission (.agent_memoire.md) : la lecture reste possible, l'écriture
        # est réservée au système.
        self.write_protected_names = set(write_protected_names or [])

        # SÉCURITÉ (anti auto-modification) : si l'outil est pointé sur son
        # PROPRE répertoire source, un agent (ou une injection) pourrait
        # réécrire sandbox.py / workers.py et neutraliser toutes les
        # protections pour les runs suivants. On protège donc en écriture
        # les fichiers système de l'application dès que la racine du projet
        # contient (ou est) le dossier de l'application.
        app_dir = Path(__file__).resolve().parent
        if self.root == app_dir or app_dir.is_relative_to(self.root):
            self.write_protected_names |= self.APP_SYSTEM_FILES
            logger.warning(
                "[SANDBOX] La racine du projet contient les fichiers de "
                "L'Atelier IA elle-même : les fichiers système "
                f"({', '.join(sorted(self.APP_SYSTEM_FILES))}) sont protégés "
                "en écriture pour cette session (auto-modification interdite).")

        self.backup_dir = self.root / ".agent_backups"
        # Dossier des rapports d'agents (publish_report) : LISIBLE par tous les
        # agents (le Codeur doit pouvoir lire la spec de l'Architecte), mais
        # PROTÉGÉ EN ÉCRITURE via les outils classiques (write_file, edit_file,
        # delete_file, rename_file). Le SEUL chemin d'écriture est la méthode
        # publish_report ci-dessous, dont le nom de fichier est choisi par le
        # SYSTÈME (inversion de contrôle : l'agent fournit uniquement le texte).
        # NB : on n'utilise PAS ".agents/" car ce dossier est déjà réservé par
        # l'application (ui.py) à la détection d'agents personnalisés du projet.
        self.reports_dir = self.root / self.REPORTS_DIRNAME
        self.reports_history_dir = self.reports_dir / "history"

    def _safe_path(self, user_path, write_mode=False):
        """Unique point de contrôle : tous les outils passent par ici."""
        candidate = (self.root / user_path).resolve(strict=False)
        
        # TOCTOU mitigation: Resolve fully if it already exists
        if candidate.exists():
            candidate = candidate.resolve(strict=True)
            
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise PermissionError(f"Accès refusé hors du projet : {user_path}")
            
        if candidate == self.backup_dir or candidate.is_relative_to(self.backup_dir):
            raise PermissionError(f"Accès refusé (dossier de sauvegarde réservé) : {user_path}")

        # Dossier des rapports d'agents : lecture libre, écriture INTERDITE via
        # les outils classiques. Le seul chemin d'écriture est publish_report,
        # dont le nom de fichier est fixé par le système, pas par l'agent.
        if write_mode and (candidate == self.reports_dir
                           or candidate.is_relative_to(self.reports_dir)):
            raise PermissionError(
                f"Accès en écriture refusé (dossier de rapports réservé à "
                f"l'outil publish_report) : {user_path}")

        # Vérification des fichiers/dossiers sensibles.
        # BUGFIX : on inspecte les parties RELATIVES à la racine du projet,
        # pas le chemin absolu complet. Sinon, un projet rangé sous un chemin
        # contenant lui-même un nom sensible (ex: /home/user/.venv/mon_projet)
        # devenait entièrement inaccessible.
        rel_parts = candidate.relative_to(self.root).parts if candidate != self.root else ()
        for part in rel_parts:
            if part in self.SENSITIVE_NAMES:
                raise PermissionError(f"Accès refusé (chemin sensible) : {user_path}")

        # Fichiers protégés en écriture (ex: mémoire persistante des missions)
        if write_mode and candidate.name in self.write_protected_names:
            raise PermissionError(
                f"Accès en écriture refusé (fichier protégé, géré par le système) : {user_path}")

        # Liste blanche pour l'écriture ou la visibilité spécifique
        if write_mode and self.use_whitelist:
            best_match_len = -1
            is_allowed = False
            
            for c_path in self.checked_paths:
                if candidate == c_path or candidate.is_relative_to(c_path):
                    match_len = len(c_path.parts)
                    if match_len > best_match_len:
                        best_match_len = match_len
                        is_allowed = True
                        
            for u_path in self.unchecked_paths:
                if candidate == u_path or candidate.is_relative_to(u_path):
                    match_len = len(u_path.parts)
                    # V4.3.0 : '>=' et non '>' — à profondeur égale (même
                    # chemin coché ET décoché), le REFUS l'emporte (deny-wins).
                    if match_len >= best_match_len:
                        best_match_len = match_len
                        is_allowed = False
                        
            if not is_allowed:
                raise PermissionError(f"Accès en écriture refusé (chemin non coché dans la liste blanche) : {user_path}")
                
        return candidate

    def whitelist_add(self, user_path):
        """Ajoute UN chemin à la liste blanche d'écriture, après accord
        EXPLICITE de l'utilisateur (voir workers.py : création d'un nouveau
        fichier hors liste blanche, confirmée via une boîte de dialogue
        force=True, jamais contournable par le mode auto-approve).
        Toutes les autres protections restent vérifiées ici : confinement à
        la racine, noms sensibles, dossier de sauvegarde ET fichiers protégés
        en écriture (mémoire persistante) — un agent ne peut donc PAS utiliser
        ce mécanisme pour faire autoriser .agent_memoire.md ou un chemin hors
        projet."""
        candidate = self._safe_path(user_path, write_mode=False)
        if candidate.name in self.write_protected_names:
            raise PermissionError(
                f"Accès en écriture refusé (fichier protégé, géré par le système) : {user_path}")
        # Le dossier de rapports ne peut pas non plus être « débloqué » par ce
        # mécanisme : _safe_path est appelé ici en mode lecture, on revérifie
        # donc explicitement.
        if candidate == self.reports_dir or candidate.is_relative_to(self.reports_dir):
            raise PermissionError(
                f"Accès en écriture refusé (dossier de rapports réservé à "
                f"l'outil publish_report) : {user_path}")
        self.checked_paths.add(candidate)
        return candidate

    # ------------------------------------------------------------------ #
    #  Publication de rapports d'agents (inversion de contrôle)           #
    # ------------------------------------------------------------------ #
    # L'agent fournit UNIQUEMENT le texte de son rapport : il ne choisit ni
    # le dossier ni le nom du fichier. Le chemin est dérivé de l'ID d'agent
    # (une valeur de configuration système, PAS une entrée du LLM), ce qui
    # supprime toute la surface d'attaque liée à la validation d'un chemin
    # choisi par le modèle. Avantages :
    #   - infaillibilité : impossible de se tromper de nom/dossier ;
    #   - prédictibilité : l'Orchestrateur sait que le rapport de l'agent X
    #     est TOUJOURS dans .agent_reports/X.md ;
    #   - vérifiabilité : l'existence et la date du fichier sont des preuves
    #     matérielles pour la vérification anti-hallucination.
    # L'ancienne version est archivée dans .agent_reports/history/ avant
    # écrasement (espace de travail propre + trace pour déboguer une mission).

    def publish_report(self, agent_id, content, header="", allowed_ids=None):
        """Écrit le rapport de l'agent 'agent_id' dans le fichier attitré
        .agent_reports/<agent_id>.md, en archivant l'ancienne version.
        Renvoie le chemin RELATIF (posix) du rapport écrit.
        NB : ce chemin est construit par le système ; il ne passe donc pas par
        _safe_path (qui, lui, sert à contrôler les chemins fournis par les
        agents). L'ID est néanmoins assaini par prudence (défense en
        profondeur : il provient de agents.json, pas du LLM).

        DÉFENSE EN PROFONDEUR (allowed_ids) : si un ensemble d'IDs autorisés est
        fourni par l'appelant (typiquement les clés de AGENTS_CONFIG), on refuse
        tout ID inconnu AVANT d'écrire quoi que ce soit. Cela garantit qu'aucun
        fichier ne peut être matérialisé pour un identifiant qui ne serait pas
        une valeur de configuration système — même si, à l'avenir, l'ID venait
        à transiter par un chemin plus proche du LLM."""
        if allowed_ids is not None and agent_id not in allowed_ids:
            raise PermissionError(
                f"publish_report refusé : agent_id inconnu '{agent_id}' "
                f"(hors configuration système).")
        safe_name = re.sub(r"[^A-Za-z0-9_\-]", "_", str(agent_id))[:64] or "agent"
        filename = f"{safe_name}.md"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        target = self.reports_dir / filename

        # Historisation avant écrasement + purge des archives trop anciennes.
        if target.exists() and target.is_file():
            self.reports_history_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            try:
                shutil.copy2(target, self.reports_history_dir / f"{safe_name}_{timestamp}.md")
                archives = sorted(self.reports_history_dir.glob(f"{safe_name}_*.md"),
                                  key=os.path.getmtime)
                if len(archives) > self.REPORTS_HISTORY_KEEP:
                    for old in archives[:-self.REPORTS_HISTORY_KEEP]:
                        old.unlink(missing_ok=True)
            except Exception:
                pass  # l'historisation ne doit jamais bloquer la publication

        target.write_text((header or "") + (content or ""), encoding="utf-8")
        return f"{self.REPORTS_DIRNAME}/{filename}"

    def list_dir(self, path="."):
        target = self._safe_path(path, write_mode=False)
        if not target.is_dir():
            raise NotADirectoryError(f"{path} n'est pas un dossier")
        return sorted(
            p.name + ("/" if p.is_dir() else "")
            for p in target.iterdir()
            # V4.3.0 : cohérence avec tree() — les noms sensibles (.env,
            # .git, ...) ne sont plus révélés aux agents par list_dir
            # (ils étaient déjà illisibles, mais leur existence fuyait).
            if p.name != ".agent_backups" and p.name not in self.SENSITIVE_NAMES
        )

    def read_file(self, path, truncate=True, start_line=None, end_line=None):
        target = self._safe_path(path, write_mode=False)
        
        if not target.exists():
            raise FileNotFoundError(f"Fichier introuvable : {path}")
            
        if target.stat().st_size > 10 * 1024 * 1024:
            raise ValueError(f"Fichier trop volumineux (>10Mo) : {path}")
            
        try:
            content = target.read_text(encoding="utf-8")
            if start_line is not None or end_line is not None:
                lines = content.splitlines(True)
                start_idx = max(0, (start_line or 1) - 1)
                end_idx = min(len(lines), end_line) if end_line else len(lines)
                content = "".join(lines[start_idx:end_idx])
                
            if truncate and len(content) > MAX_FILE_CHARS:
                # Troncature intelligente : on coupe à une fin de ligne, et on
                # indique précisément à l'agent où il en est et comment lire la
                # suite par tranches (le fichier sur disque reste intact).
                shown = content[:MAX_FILE_CHARS]
                last_nl = shown.rfind("\n")
                if last_nl > 0:
                    shown = shown[:last_nl]
                offset = (start_line or 1) - 1
                shown_lines = offset + shown.count("\n") + 1
                total_lines = offset + content.count("\n") + 1
                return shown + (
                    f"\n... [AFFICHAGE TRONQUÉ : lignes {(start_line or 1)} à {shown_lines} "
                    f"affichées sur {total_lines} au total. Le fichier sur disque est "
                    f"complet. Pour lire la suite, utilise read_file avec "
                    f"start={shown_lines + 1} et end={min(shown_lines + 400, total_lines)}, "
                    f"puis continue par tranches.]"
                )
            return content
        except UnicodeDecodeError:
            raise ValueError(f"Erreur : le fichier {path} est binaire ou n'est pas encodé en UTF-8.")

    def _backup_file(self, target):
        """Sauvegarde une copie du fichier avant écriture et nettoie les anciens backups."""
        if target.exists() and target.is_file():
            if not self.backup_dir.exists():
                try:
                    self.backup_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{target.name}_{timestamp}.bak"
            try:
                shutil.copy2(target, self.backup_dir / backup_name)
                
                # Purge (on garde les 20 plus récents pour ce fichier spécifique)
                backups = sorted(self.backup_dir.glob(f"{target.name}_*.bak"), key=os.path.getmtime)
                if len(backups) > 20:
                    for old_bak in backups[:-20]:
                        old_bak.unlink(missing_ok=True)
            except Exception as e:
                raise RuntimeError(f"Échec de la sauvegarde de {target.name} : {e}")

    def write_file(self, path, content):
        with self._file_lock:
            target = self._safe_path(path, write_mode=True)
                
            self._backup_file(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW
                
            fd = os.open(target, flags, 0o666)
            try:
                f = open(fd, 'w', encoding="utf-8")
            except Exception:
                os.close(fd)
                raise
            with f:
                f.write(content)

    def delete_file(self, path):
        with self._file_lock:
            target = self._safe_path(path, write_mode=True)
            if not target.exists():
                raise FileNotFoundError(f"Fichier introuvable : {path}")
            self._backup_file(target)
            target.unlink()

    def rename_file(self, old_path, new_path):
        with self._file_lock:
            old_target = self._safe_path(old_path, write_mode=True)
            new_target = self._safe_path(new_path, write_mode=True)
            if not old_target.exists():
                raise FileNotFoundError(f"Fichier introuvable : {old_path}")
            if new_target.exists():
                raise FileExistsError(f"La destination existe déjà : {new_path}")
            self._backup_file(old_target)
            new_target.parent.mkdir(parents=True, exist_ok=True)
            old_target.rename(new_target)


    def tree(self, max_depth=3, max_entries=400):
        """Arborescence textuelle du projet (pour donner le contexte initial)."""
        lines = []
        count = 0

        def walk(directory, prefix=""):
            nonlocal count
            try:
                entries = sorted(
                    directory.iterdir(),
                    key=lambda p: (p.is_file(), p.name.lower()),
                )
            except PermissionError:
                return
            for entry in entries:
                if count >= max_entries:
                    return
                # On ignore le bruit habituel et les fichiers sensibles
                if entry.name in self.SENSITIVE_NAMES:
                    continue
                    
                # Vérifier si c'est autorisé (si la liste blanche est utilisée)
                if self.use_whitelist:
                    is_allowed = False
                    # Le dossier de rapports est toujours visible : les agents
                    # doivent savoir que les rapports existent pour les lire
                    # (l'écriture y est de toute façon réservée à publish_report).
                    try:
                        entry_resolved = entry.resolve(strict=False)
                        if entry_resolved == self.reports_dir or entry_resolved.is_relative_to(self.reports_dir):
                            is_allowed = True
                    except Exception:
                        pass
                    for c_path in self.checked_paths:
                        try:
                            if entry.resolve(strict=False) == c_path or entry.resolve(strict=False).is_relative_to(c_path):
                                is_allowed = True
                                break
                            # If a parent is checked, children are allowed (handled above). But if a child is checked, the parent MUST be traversed to reach it.
                            if c_path.is_relative_to(entry.resolve(strict=False)):
                                is_allowed = True
                                break
                        except Exception:
                            pass
                    if not is_allowed:
                        continue
                    
                rel_depth = len(entry.relative_to(self.root).parts)
                lines.append(f"{prefix}{entry.name}" + ("/" if entry.is_dir() else ""))
                count += 1
                if entry.is_dir() and rel_depth < max_depth:
                    walk(entry, prefix + "  ")

        walk(self.root)
        return "\n".join(lines) if lines else "(dossier vide ou tout est exclu)"

    # ------------------------------------------------------------------ #
    #  Plan de fichier (outline_file)                                      #
    # ------------------------------------------------------------------ #
    # Permet aux agents de repérer la structure d'un fichier (classes,
    # fonctions, sections) SANS le lire en entier, puis de cibler leurs
    # read_file(start, end). Évite le schéma coûteux observé en mission :
    # relire le même gros fichier par petites tranches successives.
    OUTLINE_MAX_ITEMS = 200

    def outline_file(self, path):
        """Renvoie le plan d'un fichier avec les numéros de ligne."""
        target = self._safe_path(path, write_mode=False)
        if not target.exists():
            raise FileNotFoundError(f"Fichier introuvable : {path}")
        if target.is_dir():
            raise ValueError(f"{path} est un dossier : utilise list_dir.")
        if target.stat().st_size > 10 * 1024 * 1024:
            raise ValueError(f"Fichier trop volumineux (>10Mo) : {path}")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"Erreur : le fichier {path} est binaire ou n'est pas encodé en UTF-8.")

        total_lines = content.count("\n") + 1
        ext = target.suffix.lower()
        warning = ""

        if ext in (".py", ".pyw"):
            items, warning = self._outline_python(content)
        elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            items = self._outline_regex(content, [
                r'^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+[A-Za-z_$][\w$]*',
                r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*[A-Za-z_$][\w$]*\s*\(',
                r'^\s*(?:export\s+)?(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>',
                r'^\s{0,4}[A-Za-z_$][\w$]*\s*\([^)]*\)\s*\{\s*$',
            ])
        elif ext in (".md", ".markdown"):
            items = self._outline_regex(content, [r'^#{1,6}\s+\S'])
        elif ext in (".html", ".htm"):
            items = self._outline_regex(content, [
                r'^\s*<(?:script|style|body|head|form|table|section|main|nav|header|footer|template|dialog)\b',
                r'^\s*<\w+[^>]*\bid="[^"]+"',
            ])
        elif ext in (".css", ".scss"):
            items = self._outline_regex(content, [r'^[^\s/@].*\{\s*$', r'^@(?:media|keyframes|font-face)\b'])
        else:
            return (f"Plan non disponible pour ce type de fichier ({ext or 'sans extension'}). "
                    f"Le fichier fait {total_lines} lignes : utilise read_file.")

        if not items:
            return (f"Plan de {path} : aucun élément structurel détecté "
                    f"({total_lines} lignes). Utilise read_file pour le lire.")

        items.sort(key=lambda t: t[0])
        truncated = ""
        if len(items) > self.OUTLINE_MAX_ITEMS:
            items = items[:self.OUTLINE_MAX_ITEMS]
            truncated = f"\n... [plan tronqué à {self.OUTLINE_MAX_ITEMS} éléments]"

        width = len(str(total_lines))
        out = [f"Plan de {path} ({total_lines} lignes) :"]
        if warning:
            out.append(warning)
        for lineno, end, depth, label in items:
            span = f"(lignes {lineno}-{end})" if end and end > lineno else ""
            out.append(f"{str(lineno).rjust(width)}| {'  ' * depth}{label}  {span}".rstrip())
        out.append(truncated + "\nAstuce : utilise read_file avec start/end pour lire "
                   "directement la section qui t'intéresse (en une seule fois).")
        return "\n".join(out)

    @staticmethod
    def _outline_python(content):
        """Plan d'un fichier Python via l'AST (classes, fonctions, méthodes).
        Renvoie (items, warning) avec items = [(lineno, end_lineno, depth, label)]."""
        import ast
        items = []
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            # Fallback regex si le fichier ne compile pas : plan approximatif.
            for i, line in enumerate(content.splitlines(), 1):
                m = re.match(r'^(\s*)(async\s+def|def|class)\s+(\w+)', line)
                if m:
                    depth = len(m.group(1).expandtabs(4)) // 4
                    items.append((i, i, depth, f"{m.group(2)} {m.group(3)}"))
            return items, f"⚠️ Erreur de syntaxe ligne {e.lineno} : plan approximatif (regex)."

        def visit(node, depth):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if isinstance(child, ast.ClassDef):
                        label = f"class {child.name}"
                    else:
                        args = ", ".join(a.arg for a in child.args.args)
                        kw = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                        label = f"{kw} {child.name}({args})"
                    end = getattr(child, "end_lineno", child.lineno)
                    items.append((child.lineno, end, depth, label))
                    visit(child, depth + 1)
                else:
                    visit(child, depth)

        visit(tree, 0)
        return items, ""

    @staticmethod
    def _outline_regex(content, patterns):
        """Plan générique par regex, une ligne = un élément potentiel."""
        compiled = [re.compile(p) for p in patterns]
        items = []
        for i, line in enumerate(content.splitlines(), 1):
            for rx in compiled:
                if rx.search(line[:500]):
                    items.append((i, i, 0, line.strip()[:100]))
                    break
        return items
        
    def run_linter_fix(self, rel_path, timeout=60):
        """Exécute ruff check --fix et ruff format sur un fichier spécifique de la sandbox."""
        target_path = self._safe_path(rel_path, write_mode=True)
        
        # Pour des raisons de sécurité, on résout le chemin de python explicitement
        python_bin = sys.executable
        if not os.path.isabs(python_bin):
            python_bin = resolve_external_binary(python_bin) or sys.executable
            
        cmd1 = [python_bin, "-m", "ruff", "check", "--fix", "-q", target_path]
        cmd2 = [python_bin, "-m", "ruff", "format", "-q", target_path]
        try:
            env = hardened_subprocess_env()
            subprocess.run(cmd1, cwd=self.root, capture_output=True, text=True, timeout=timeout, env=env)
            subprocess.run(cmd2, cwd=self.root, capture_output=True, text=True, timeout=timeout, env=env)
            return "OK"
        except subprocess.TimeoutExpired:
            return "ÉCHEC : le linter a dépassé le délai imparti."
        except Exception as e:
            return f"ÉCHEC : {e}"

    def run_command(self, command, timeout=30):
        """Désactivé pour des raisons de sécurité."""
        return "ERREUR CRITIQUE : L'exécution de commandes système a été désactivée par mesure de sécurité."

    # ------------------------------------------------------------------ #
    #  Exécution de commandes en LISTE BLANCHE (run_tests)                #
    # ------------------------------------------------------------------ #
    # Contrairement à run_command (désactivé), l'agent ne compose PAS la
    # commande : il choisit un identifiant parmi cette liste fermée, dont
    # les argv sont fixés ici, côté système. Aucun argument fourni par
    # l'agent n'est injecté dans la ligne de commande.
    # ⚠️ pytest a été RETIRÉ de cette liste par mesure de sécurité : le
    # lancer revient à exécuter le code du projet (conftest.py, imports...).
    # Les commandes restantes n'exécutent pas le code du projet, mais la
    # confirmation utilisateur reste TOUJOURS exigée côté worker, même en
    # mode auto-approve (défense en profondeur).
    ALLOWED_COMMANDS = {
        "compileall": [sys.executable, "-m", "compileall", "-q", "."],
        "ruff":       [sys.executable, "-m", "ruff", "check", "."],
        # SÉCURITÉ (V4.3.0) : 'git diff' sur un dépôt hostile peut exécuter
        # du code via un driver textconv déclaré dans .git/config +
        # .gitattributes (le textconv s'applique PAR DÉFAUT, contrairement
        # à --ext-diff) — la même classe de risque qui a motivé le retrait
        # de pytest. On neutralise textconv, ext-diff et le pager.
        "git_diff":   ["git", "--no-pager", "-c", "core.pager=cat",
                       "diff", "--no-textconv", "--no-ext-diff"],
    }
    COMMAND_OUTPUT_MAX_CHARS = 8000

    def run_named_command(self, command_id, timeout=120):
        """Exécute une commande prédéfinie de la liste blanche, dans la racine
        du projet, avec timeout. Renvoie la sortie formatée pour l'agent."""
        if command_id not in self.ALLOWED_COMMANDS:
            raise ValueError(
                f"Commande inconnue '{command_id}'. "
                f"Autorisées : {', '.join(sorted(self.ALLOWED_COMMANDS))}")
        argv = list(self.ALLOWED_COMMANDS[command_id])
        # SÉCURITÉ (V4.3.0) : jamais de nom d'exécutable nu avec cwd=projet
        # (sous Windows, le cwd est inclus dans la recherche de CreateProcess,
        # donc un binaire homonyme déposé dans un dépôt hostile serait lancé).
        # On résout via le PATH de l'application et on passe un chemin absolu.
        if not os.path.isabs(argv[0]):
            resolved = resolve_external_binary(argv[0])
            if not resolved:
                return (f"ÉCHEC : impossible de lancer '{command_id}' "
                        f"(binaire '{argv[0]}' introuvable sur le PATH).")
            argv[0] = resolved
        try:
            proc = subprocess.run(
                argv, cwd=self.root, capture_output=True, text=True,
                timeout=timeout, env=hardened_subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            return (f"ÉCHEC : la commande '{command_id}' a dépassé le délai de "
                    f"{timeout}s et a été interrompue (boucle infinie dans le code ?).")
        except FileNotFoundError as e:
            return f"ÉCHEC : impossible de lancer '{command_id}' ({e})."

        output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        if not output:
            output = "(aucune sortie)"
        if len(output) > self.COMMAND_OUTPUT_MAX_CHARS:
            # On garde le début ET la fin : le résumé/les erreurs des outils
            # de vérification sont généralement en fin de sortie.
            half = self.COMMAND_OUTPUT_MAX_CHARS // 2
            output = (output[:half]
                      + "\n... [sortie tronquée au milieu] ...\n"
                      + output[-half:])
        status = "SUCCÈS (code retour 0)" if proc.returncode == 0 else f"ÉCHEC (code retour {proc.returncode})"
        return f"Commande '{command_id}' terminée : {status}\n--- SORTIE ---\n{output}"

    def run_python_script(self, script_path, timeout=60):
        """Exécute un script Python dans l'environnement du projet."""
        target = self._safe_path(script_path, write_mode=False)
        if not target.exists():
            return f"ÉCHEC : Le fichier {script_path} n'existe pas."
            
        fallback = True
        if DOCKER_AVAILABLE:
            try:
                client = docker.from_env()
                client.ping()
                
                # Chemin relatif pour le script monté dans le volume
                rel_script = target.relative_to(self.root).as_posix()
                
                # Installation des requirements si présents, puis exécution
                command = f'bash -c "if [ -f requirements.txt ]; then pip install -q -r requirements.txt; fi && python {rel_script}"'
                
                container = client.containers.run(
                    "python:3.10-slim",
                    command=command,
                    volumes={str(self.root): {'bind': '/project', 'mode': 'rw'}},
                    working_dir="/project",
                    network_disabled=False, # Requis pour pip install
                    detach=True
                )
                
                try:
                    result = container.wait(timeout=timeout)
                    output = container.logs().decode('utf-8', errors='replace').strip()
                    container.remove(force=True)
                    returncode = result.get('StatusCode', 1)
                    
                    if not output:
                        output = "(aucune sortie)"
                        
                    if len(output) > self.COMMAND_OUTPUT_MAX_CHARS:
                        half = self.COMMAND_OUTPUT_MAX_CHARS // 2
                        output = (output[:half] + "\n... [sortie tronquée au milieu] ...\n" + output[-half:])
                        
                    status = "SUCCÈS" if returncode == 0 else f"ÉCHEC (code retour {returncode})"
                    return f"Exécution (Docker) de {target.name} : {status}\n--- SORTIE ---\n{output}"
                    
                except requests.exceptions.ReadTimeout:
                    container.stop(timeout=1)
                    container.remove(force=True)
                    return f"ÉCHEC : l'exécution (Docker) a dépassé le délai de {timeout}s."
            except Exception as e:
                logger.warning(f"[SANDBOX] Erreur Docker, repli sur sous-processus local: {e}")
                fallback = True
                
        if fallback:
            bootstrap_code = f"""
import sys, runpy

def security_hook(event, args):
    if event in ('os.system', 'os.spawn', 'os.exec', 'os.posix_spawn', 'subprocess.Popen'):
        raise PermissionError("INTERDIT : L'exécution de processus système est désactivée par sécurité (Audit Hook).")

sys.addaudithook(security_hook)

try:
    runpy.run_path(r'{target.as_posix()}', run_name='__main__')
except SystemExit:
    pass
except Exception as e:
    import traceback
    traceback.print_exc()
"""
            argv = [sys.executable, "-c", bootstrap_code]
            try:
                proc = subprocess.run(
                    argv, cwd=self.root, capture_output=True, text=True,
                    timeout=timeout, env=hardened_subprocess_env(),
                )
            except subprocess.TimeoutExpired:
                return f"ÉCHEC : l'exécution a dépassé le délai de {timeout}s."
            except Exception as e:
                return f"ÉCHEC : impossible de lancer le script ({e})."
    
            output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
            if not output:
                output = "(aucune sortie)"
                
            if len(output) > self.COMMAND_OUTPUT_MAX_CHARS:
                half = self.COMMAND_OUTPUT_MAX_CHARS // 2
                output = (output[:half]
                          + "\n... [sortie tronquée au milieu] ...\n"
                          + output[-half:])
                
            status = "SUCCÈS" if proc.returncode == 0 else f"ÉCHEC (code retour {proc.returncode})"
            return f"Exécution de {target.name} : {status}\n--- SORTIE ---\n{output}"

    def grep(self, pattern, paths=None):
        if paths is None:
            paths = ["."]
            
        try:
            # Vérification syntaxique rapide avant de lancer le process
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Regex invalide : {e}")

        max_matches = 200
        timeout_seconds = 3.0

        # Collecte des fichiers
        files_to_search = []
        for p in paths:
            try:
                target = self._safe_path(p, write_mode=False)
            except PermissionError:
                continue
                
            if target.is_file():
                files_to_search.append((str(target), p))
            elif target.is_dir():
                for root, _, files in os.walk(target):
                    # BUGFIX (V4.3.0) : on inspecte les parties RELATIVES à
                    # la racine du projet (même correctif que _safe_path),
                    # pas le chemin absolu. Sinon un projet rangé sous un
                    # chemin contenant lui-même un nom sensible (ex:
                    # /home/user/.venv/mon_projet) rendait grep muet
                    # ("Aucun fichier à analyser") alors que read_file
                    # fonctionnait.
                    try:
                        rel_parts = Path(root).resolve().relative_to(self.root).parts
                    except ValueError:
                        rel_parts = Path(root).parts
                    if any(part in self.SENSITIVE_NAMES for part in rel_parts):
                        continue
                    for f in files:
                        file_path = Path(root) / f
                        try:
                            # Re-check via _safe_path to respect checked_paths
                            self._safe_path(file_path.relative_to(self.root), write_mode=False)
                            files_to_search.append((str(file_path), file_path.relative_to(self.root).as_posix()))
                        except PermissionError:
                            continue

        if not files_to_search:
            return "Aucun fichier à analyser."

        ctx = multiprocessing.get_context('spawn')
        queue = ctx.Queue()
        p = ctx.Process(target=_safe_grep_all_worker, args=(pattern, files_to_search, queue, max_matches))
        p.start()
        p.join(timeout=timeout_seconds)
        
        if p.is_alive():
            # SIGTERM d'abord, mais un process bloqué dans le moteur regex C
            # peut ne pas y répondre immédiatement : on borne le join, puis on
            # escalade en SIGKILL (kill) en dernier recours. Ainsi le thread
            # appelant ne peut jamais rester bloqué indéfiniment ici.
            p.terminate()
            p.join(timeout=2.0)
            if p.is_alive():
                p.kill()
                p.join(timeout=2.0)
            return f"ÉCHEC : La recherche a été interrompue après {timeout_seconds}s. La regex est probablement trop complexe (ReDoS potentiel)."
        
        try:
            results = queue.get_nowait()
            if isinstance(results, Exception):
                raise ValueError(f"Erreur interne lors de la recherche : {results}")
        except Exception:
            results = []

        if not results:
            return "Aucun résultat trouvé."
        return "\n".join(results)

    def graphify_build(self, target_dir="."):
        """Construit ou met à jour le graphe structurel Graphify (graph.json).

        SÉCURITÉ / ARCHITECTURE (v4.2.0) : le binaire tiers 'graphify' est
        désormais TOUJOURS lancé en mode '--code-only' :
          - la clé API n'est JAMAIS transmise à ce binaire lors du build
            (suppression de l'exposition de GEMINI_API_KEY à un exécutable
            externe pour cette étape) ;
          - l'enrichissement sémantique n'est plus délégué à graphify : le
            rapport GRAPH_REPORT.md est généré par le LLM de l'application
            (GraphifyAnalysisWorker) à partir de graph.json.
        NB : le message de succès référence 'graphify-out/' (et non plus
        'graph-out/'), en cohérence avec les chemins lus partout ailleurs
        dans l'application (analyse, visualisation)."""
        graphify_bin = resolve_external_binary("graphify")
        if not graphify_bin:
            return ("Impossible de lancer graphify : binaire introuvable sur "
                    "le PATH de l'application. Assurez-vous qu'il est installé.")
        try:
            proc = subprocess.run(
                [graphify_bin, target_dir, "--code-only", "--out", "."],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=300,
                env=hardened_subprocess_env()
            )
            if proc.returncode == 0:
                return (f"Graphe Graphify (structure seule) généré avec succès pour '{target_dir}' dans "
                        "'graphify-out/'. Utilisez « 🧠 Analyse Graphify » pour "
                        "générer GRAPH_REPORT.md via votre LLM.")
            else:
                return f"Erreur lors de la génération du graphe:\n{proc.stderr or ''}"
        except Exception as e:
            return f"Impossible de lancer graphify : {e}. Assurez-vous qu'il est installé."

    def graphify_query(self, query, api_key=None):
        """Interroge le graphe avec une question en langage naturel."""
        graphify_bin = resolve_external_binary("graphify")
        if not graphify_bin:
            return "Impossible de requêter graphify : binaire introuvable sur le PATH."
        try:
            env = hardened_subprocess_env()
            if api_key:
                env["GEMINI_API_KEY"] = api_key
                
            proc = subprocess.run(
                [graphify_bin, "query", query],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                env=env,
                timeout=30
            )
            if proc.returncode == 0:
                return proc.stdout.strip() if proc.stdout else "Aucun résultat pertinent trouvé."
            else:
                err_msg = proc.stderr or ""
                if api_key:
                    err_msg = err_msg.replace(api_key, "[CLÉ API MASQUÉE]")
                return f"Erreur lors de la requête Graphify:\n{err_msg}"
        except Exception as e:
            return f"Impossible de requêter graphify : {e}"

    def graphify_path(self, node_a, node_b, api_key=None):
        """Trouve le chemin entre deux nœuds dans le graphe."""
        graphify_bin = resolve_external_binary("graphify")
        if not graphify_bin:
            return "Impossible de chercher un chemin graphify : binaire introuvable sur le PATH."
        try:
            env = hardened_subprocess_env()
            if api_key:
                env["GEMINI_API_KEY"] = api_key
                
            proc = subprocess.run(
                [graphify_bin, "path", node_a, node_b],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                env=env,
                timeout=30
            )
            if proc.returncode == 0:
                return proc.stdout.strip() if proc.stdout else "Aucun chemin trouvé."
            else:
                err_msg = proc.stderr or ""
                if api_key:
                    err_msg = err_msg.replace(api_key, "[CLÉ API MASQUÉE]")
                return f"Erreur lors de la recherche de chemin Graphify:\n{err_msg}"
        except Exception as e:
            return f"Impossible de chercher un chemin graphify : {e}"

    def download_mcp_kicad_part(self, mpn):
        """Télécharge la librairie KiCad (symbole + empreinte) pour un composant depuis pcbparts.dev.
        Renvoie un message de statut indiquant si les fichiers ont été téléchargés ou non."""
        import urllib.request
        import json
        
        url = "https://pcbparts.dev/mcp"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cse_get_kicad",
                "arguments": {"query": mpn}
            }
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_json = json.loads(line[6:])
                        if 'error' in data_json:
                            return f"Erreur du MCP : {data_json['error']}"
                        
                        if 'result' in data_json and 'structuredContent' in data_json['result']:
                            structured = data_json['result']['structuredContent']
                            if 'error' in structured:
                                return f"Erreur lors de la recherche du composant : {structured['error']}"
                                
                            sym = structured.get('kicad_symbol')
                            mod = structured.get('kicad_footprint')
                            if not sym or not mod:
                                return "Le composant a été trouvé mais n'a pas de modèle KiCad disponible."
                            
                            # SÉCURITÉ (V4.4.0) : le MPN provient de l'AGENT
                            # (donc du LLM, donc potentiellement d'une injection
                            # de prompt logée dans le dépôt). L'ancien code
                            # construisait le nom de fichier sans passer par
                            # _safe_path : un mpn du type '../../x' écrivait
                            # HORS de kicad_libs/, voire hors du projet.
                            # Assainissement identique à publish_report +
                            # re-vérification du confinement (défense en
                            # profondeur).
                            safe_mpn = re.sub(r"[^A-Za-z0-9_\-\.]", "_",
                                              str(mpn)).strip(".")[:64] or "part"
                            lib_dir = (self.root / "kicad_libs")
                            lib_dir.mkdir(parents=True, exist_ok=True)
                            lib_dir = lib_dir.resolve()
                            
                            sym_path = lib_dir / f"{safe_mpn}.kicad_sym"
                            mod_path = lib_dir / f"{safe_mpn}.kicad_mod"
                            for p in (sym_path, mod_path):
                                if p.resolve().parent != lib_dir:
                                    return ("REFUSÉ (sandbox) : nom de composant "
                                            "invalide (tentative d'écriture hors "
                                            "de kicad_libs/).")
                            
                            sym_path.write_text(sym, encoding="utf-8")
                            mod_path.write_text(mod, encoding="utf-8")
                            
                            # Automatisation KiCad : Enregistrement de la librairie d'empreintes et de symboles
                            for table_name, table_header in [("fp-lib-table", "fp_lib_table"), ("sym-lib-table", "sym_lib_table")]:
                                lib_path = self.root / table_name
                                lib_entry = f'  (lib (name "kicad_libs")(type "KiCad")(uri "${{KIPRJMOD}}/kicad_libs")(options "")(descr "Local downloaded library"))\n'
                                if not lib_path.exists():
                                    lib_path.write_text(f"({table_header}\n{lib_entry})\n", encoding="utf-8")
                                else:
                                    current_lib = lib_path.read_text(encoding="utf-8")
                                    if '"kicad_libs"' not in current_lib and current_lib.strip().endswith(")"):
                                        new_lib = current_lib.rstrip()[:-1] + "\n" + lib_entry + ")"
                                        lib_path.write_text(new_lib, encoding="utf-8")
                            
                            note = ""
                            if safe_mpn != str(mpn):
                                note = (f"\n(NB : le nom '{mpn}' contenait des "
                                        f"caractères interdits, fichiers nommés "
                                        f"'{safe_mpn}'.)")
                            
                            # Extraction du VRAI nom du symbole pour guider l'agent (anti-hallucination)
                            actual_sym_name = mpn
                            match = re.search(r'\(symbol\s+"([^"]+)"', sym)
                            if match:
                                actual_sym_name = match.group(1)
                                
                            return f"SUCCÈS : Les fichiers KiCad pour {mpn} ont été téléchargés dans :\n- {sym_path.relative_to(self.root)}\n- {mod_path.relative_to(self.root)}{note}\n\n⚠️ IMPORTANT POUR SKIDL : Le vrai nom interne du composant est '{actual_sym_name}'. Tu DOIS utiliser CE nom exact dans ton code SKiDL, par exemple : Part('kicad_libs/{safe_mpn}.kicad_sym', '{actual_sym_name}', footprint='...')"
                        
            return "ÉCHEC : Réponse inattendue du serveur MCP."
        except Exception as e:
            return f"ÉCHEC de la connexion au serveur MCP : {e}"

    def search_mcp_pcbparts(self, query, limit=5):
        """Recherche un composant sur pcbparts.dev (MCP)."""
        import urllib.request
        import json
        
        url = "https://pcbparts.dev/mcp"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "jlc_search",
                "arguments": {"query": query, "limit": limit}
            }
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_json = json.loads(line[6:])
                        if 'error' in data_json:
                            return (False, f"Erreur du MCP : {data_json['error']}")
                        
                        if 'result' in data_json and 'structuredContent' in data_json['result']:
                            structured = data_json['result']['structuredContent']
                            if 'error' in structured:
                                return (False, f"Erreur lors de la recherche du composant : {structured['error']}")
                                
                            results = structured.get('results', [])
                            if not results:
                                return (False, "Aucun composant trouvé.")
                            
                            return (True, results)
                        
            return (False, "ÉCHEC : Réponse inattendue du serveur MCP.")
        except Exception as e:
            return (False, f"ÉCHEC de la connexion au serveur MCP : {e}")

    def search_kicad_footprint(self, keyword):
        """Recherche une empreinte dans les librairies KiCad locales."""
        import os
        
        # On teste les chemins d'installation par défaut sur Windows
        kicad_dir = os.environ.get("KICAD9_FOOTPRINT_DIR")
        if not kicad_dir:
            for version in ["9.0", "8.0", "7.0"]:
                path = rf"C:\Program Files\KiCad\{version}\share\kicad\footprints"
                if os.path.isdir(path):
                    kicad_dir = path
                    break
        
        if not kicad_dir or not os.path.isdir(kicad_dir):
            return "ERREUR : Dossier des empreintes KiCad introuvable."
        
        keyword_lower = keyword.lower()
        results = []
        for root, dirs, files in os.walk(kicad_dir):
            if not root.endswith(".pretty"):
                continue
            lib_name = os.path.basename(root).replace(".pretty", "")
            for file in files:
                if file.endswith(".kicad_mod") and keyword_lower in file.lower():
                    footprint_name = file.replace(".kicad_mod", "")
                    results.append(f"{lib_name}:{footprint_name}")
                    if len(results) >= 50:
                        results.append("... (plus de 50 résultats, affinez la recherche)")
                        return "\n".join(results)
        
        if not results:
            return f"Aucune empreinte trouvée pour '{keyword}'."
        return "\n".join(results)

    def build_vector_index(self):
        """Construit l'index RAG à partir du graph.json généré par Graphify."""
        try:
            from core.rag_engine import GraphRagEngine
            engine = GraphRagEngine(self.root)
            nb_indexed = engine.build_index()
            return f"SUCCÈS: Index RAG construit avec {nb_indexed} nœuds."
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            return f"ERREUR lors de la construction de l'index RAG: {e}\n{tb}"

    def search_codebase(self, query, top_k=3):
        """
        Recherche sémantique dans la codebase à l'aide de l'index RAG.
        Renvoie le code pertinent ainsi que le contexte des dépendances.
        """
        try:
            from core.rag_engine import GraphRagEngine
            engine = GraphRagEngine(self.root)
            results = engine.search(query, int(top_k))
            
            if not results:
                return f"Aucun résultat pertinent trouvé pour '{query}'."
                
            output = []
            for r in results:
                entry = f"--- Nœud: {r['label']} (Fichier: {r['file']}, {r['location']}) ---\n"
                if r['graph_context']:
                    entry += "Contexte Graphify:\n" + "\n".join(["- " + c for c in r['graph_context']]) + "\n"
                entry += "Code Source:\n" + r['content'] + "\n"
                output.append(entry)
                
            return "\n".join(output)
            
        except Exception as e:
            return f"ERREUR lors de la recherche dans la codebase: {e}"
