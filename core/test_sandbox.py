import pytest
from pathlib import Path
from core.sandbox import FileSandbox

def test_safe_path_basic(tmp_path):
    sandbox = FileSandbox(tmp_path)
    # Check inside root
    safe = sandbox._safe_path("test.txt")
    assert safe == tmp_path / "test.txt"

def test_safe_path_traversal(tmp_path):
    sandbox = FileSandbox(tmp_path)
    # Check directory traversal attack
    with pytest.raises(PermissionError, match="hors du projet"):
        sandbox._safe_path("../outside.txt")

def test_safe_path_sensitive(tmp_path):
    sandbox = FileSandbox(tmp_path)
    # Check sensitive files blocking
    with pytest.raises(PermissionError, match="chemin sensible"):
        sandbox._safe_path(".env")
    with pytest.raises(PermissionError, match="chemin sensible"):
        sandbox._safe_path(".git/config")
    with pytest.raises(PermissionError, match="sauvegarde réservé"):
        sandbox._safe_path(".agent_backups/file.bak")

def test_safe_path_whitelist_write(tmp_path):
    allowed_dir = tmp_path / "src"
    allowed_dir.mkdir()
    allowed_file = allowed_dir / "main.py"
    allowed_file.touch()
    
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other_file = other_dir / "other.py"
    other_file.touch()

    sandbox = FileSandbox(tmp_path, checked_paths=[str(allowed_dir)])
    
    # Read should be allowed everywhere
    sandbox._safe_path("other/other.py", write_mode=False)
    
    # Write inside whitelist
    sandbox._safe_path("src/main.py", write_mode=True)
    
    # Write outside whitelist
    with pytest.raises(PermissionError, match="chemin non coché"):
        sandbox._safe_path("other/other.py", write_mode=True)

def test_safe_path_symlink(tmp_path):
    # Prepare external directory and target file
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    target_file = external_dir / "secret.txt"
    target_file.touch()

    # Prepare project root and sandbox
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    sandbox = FileSandbox(project_dir)

    # Create a symlink in the project pointing outside
    symlink_path = project_dir / "link_to_secret"
    try:
        symlink_path.symlink_to(target_file)
    except OSError:
        # On Windows, symlink creation requires admin privileges by default. 
        # If it fails, skip the test.
        pytest.skip("Symlink creation requires administrative privileges on Windows")

    # Should raise a PermissionError
    with pytest.raises(PermissionError, match="hors du projet"):
        sandbox._safe_path("link_to_secret", write_mode=False)

def test_write_protected_names(tmp_path):
    """La mémoire persistante est lisible mais protégée en écriture."""
    memory = tmp_path / ".agent_memoire.md"
    memory.write_text("souvenirs", encoding="utf-8")
    sandbox = FileSandbox(tmp_path, write_protected_names={".agent_memoire.md"})

    # Lecture autorisée
    assert sandbox.read_file(".agent_memoire.md") == "souvenirs"

    # Écriture / suppression / renommage refusés
    with pytest.raises(PermissionError, match="fichier protégé"):
        sandbox._safe_path(".agent_memoire.md", write_mode=True)
    with pytest.raises(PermissionError, match="fichier protégé"):
        sandbox.write_file(".agent_memoire.md", "injection")
    with pytest.raises(PermissionError, match="fichier protégé"):
        sandbox.delete_file(".agent_memoire.md")
    # Renommer un autre fichier VERS le nom protégé est aussi refusé
    other = tmp_path / "notes.md"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(PermissionError, match="fichier protégé"):
        sandbox.rename_file("notes.md", ".agent_memoire.md")


def test_root_under_sensitive_path(tmp_path):
    """Un projet rangé sous un chemin contenant un nom sensible (ex: .venv)
    doit rester accessible : seuls les chemins RELATIFS au projet comptent."""
    project = tmp_path / ".venv" / "mon_projet"
    project.mkdir(parents=True)
    f = project / "main.py"
    f.write_text("print('ok')", encoding="utf-8")

    sandbox = FileSandbox(project)
    # Accès normal au fichier du projet
    assert "print" in sandbox.read_file("main.py")
    # Mais un .venv INTERNE au projet reste bloqué
    with pytest.raises(PermissionError, match="chemin sensible"):
        sandbox._safe_path(".venv/lib.py")


def test_run_named_command_whitelist(tmp_path):
    """Seuls les identifiants de la liste blanche sont acceptés."""
    sandbox = FileSandbox(tmp_path)
    with pytest.raises(ValueError, match="Commande inconnue"):
        sandbox.run_named_command("rm -rf /")
    with pytest.raises(ValueError, match="Commande inconnue"):
        sandbox.run_named_command("pytest; echo pwned")


def test_run_named_command_compileall(tmp_path):
    """compileall détecte une erreur de syntaxe et réussit sur du code valide."""
    project = tmp_path / "project"
    project.mkdir()
    sandbox = FileSandbox(project)

    good = project / "good.py"
    good.write_text("print('ok')\n", encoding="utf-8")
    res = sandbox.run_named_command("compileall")
    assert "SUCCÈS" in res

    bad = project / "bad.py"
    bad.write_text("def broken(:\n", encoding="utf-8")
    res = sandbox.run_named_command("compileall")
    assert "ÉCHEC" in res


def test_run_named_command_cwd_is_root(tmp_path):
    """La commande s'exécute bien dans la racine du projet (pas ailleurs)."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "ok.py").write_text("x = 1\n", encoding="utf-8")
    sandbox = FileSandbox(project)
    res = sandbox.run_named_command("compileall")
    assert "SUCCÈS" in res


def test_grep(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    sandbox = FileSandbox(project_dir)

    file1 = project_dir / "file1.txt"
    file1.write_text("Hello world\nThis is a test\nGoodbye")

    file2 = project_dir / "file2.txt"
    file2.write_text("Another test here\nNo greeting")

    # Test basic match
    res = sandbox.grep("test", ["file1.txt", "file2.txt"])
    assert "file1.txt:2: This is a test" in res
    assert "file2.txt:1: Another test here" in res

    # Test no match
    res = sandbox.grep("foo")
    assert "Aucun résultat trouvé" in res


# ---------------------------------------------------------------------------
#  outline_file (plan de fichier)
# ---------------------------------------------------------------------------

def test_outline_python(tmp_path):
    """Le plan d'un fichier Python liste classes, méthodes et fonctions avec lignes."""
    code = (
        "import os\n\n"
        "class Foo:\n"
        "    def bar(self, x):\n"
        "        return x\n\n"
        "    async def baz(self):\n"
        "        pass\n\n"
        "def top_level(a, b):\n"
        "    return a + b\n"
    )
    (tmp_path / "mod.py").write_text(code, encoding="utf-8")
    sandbox = FileSandbox(tmp_path)
    res = sandbox.outline_file("mod.py")
    assert "class Foo" in res
    assert "def bar(self, x)" in res
    assert "async def baz(self)" in res
    assert "def top_level(a, b)" in res
    assert "lignes 3-8" in res  # class Foo s'étend des lignes 3 à 8


def test_outline_python_syntax_error(tmp_path):
    """Fichier Python invalide : plan approximatif via regex + avertissement."""
    (tmp_path / "bad.py").write_text("class Foo:\n    def broken(:\n", encoding="utf-8")
    sandbox = FileSandbox(tmp_path)
    res = sandbox.outline_file("bad.py")
    assert "class Foo" in res
    assert "approximatif" in res


def test_outline_unsupported_ext(tmp_path):
    (tmp_path / "data.bin.txt").write_text("juste du texte", encoding="utf-8")
    sandbox = FileSandbox(tmp_path)
    res = sandbox.outline_file("data.bin.txt")
    assert "Plan non disponible" in res


def test_outline_respects_sandbox(tmp_path):
    sandbox = FileSandbox(tmp_path)
    with pytest.raises(PermissionError, match="hors du projet"):
        sandbox.outline_file("../outside.py")


# ---------------------------------------------------------------------------
#  flexible_search (matching tolérant d'edit_file, défini dans utils.py)
# ---------------------------------------------------------------------------
from core.utils import flexible_search


def test_flexible_search_exact():
    original = "a\nb\nc\n"
    res = flexible_search(original, "b\n", "B\n")
    assert res["found"] and res["mode"] == "exact" and res["occurrences"] == 1
    assert original[res["start"]:res["end"]] == "b\n"


def test_flexible_search_trailing_whitespace():
    """Le fichier contient des espaces de fin de ligne absents du bloc search."""
    original = "def foo():   \n    return 1  \n"
    search = "def foo():\n    return 1"
    res = flexible_search(original, search, "def foo():\n    return 2")
    assert res["found"] and res["mode"] == "trailing_ws"
    new = original[:res["start"]] + res["replace"] + original[res["end"]:]
    assert "return 2" in new and "return 1" not in new


def test_flexible_search_indent_shift():
    """Bloc search avec indentation décalée uniformément : trouvé, et le
    replace est réindenté du même décalage."""
    original = "class A:\n    def f(self):\n        return 1\n"
    search = "def f(self):\n    return 1"          # 4 espaces de moins
    replace = "def f(self):\n    return 2"
    res = flexible_search(original, search, replace)
    assert res["found"] and res["mode"] == "indent"
    new = original[:res["start"]] + res["replace"] + original[res["end"]:]
    assert new == "class A:\n    def f(self):\n        return 2\n"


def test_flexible_search_no_false_positive_on_first_line_indent():
    """Le mode trailing_ws ne doit PAS tolérer l'indentation de la 1re ligne
    (ancrage en début de ligne) : sur un bloc multi-lignes désindenté, c'est
    le mode indent qui prend le relais, avec réindentation correcte."""
    original = "  x = compute()\n  print(x)\n"
    search = "x = compute()\nprint(x)"      # indentation manquante partout
    res = flexible_search(original, search, "x = compute()\nprint(x * 2)")
    assert res["mode"] == "indent"
    new = original[:res["start"]] + res["replace"] + original[res["end"]:]
    assert new == "  x = compute()\n  print(x * 2)\n"


def test_flexible_search_uniqueness_preserved():
    """Les occurrences multiples sont bien comptées dans tous les modes."""
    original = "a = 1  \nb\na = 1\n"
    res = flexible_search(original, "a = 1", "a = 2")
    assert res["occurrences"] == 2  # l'appelant refusera (bloc non unique)


def test_flexible_search_not_found():
    res = flexible_search("hello\n", "absent", "x")
    assert not res["found"] and res["occurrences"] == 0


# ---------------------------------------------------------------------------
#  whitelist_add (autorisation explicite de création hors liste blanche)
# ---------------------------------------------------------------------------

def test_whitelist_add_new_file(tmp_path):
    """Après whitelist_add, un nouveau fichier hors liste devient inscriptible."""
    allowed = tmp_path / "src"
    allowed.mkdir()
    sandbox = FileSandbox(tmp_path, checked_paths=[str(allowed)])

    # Avant : refusé
    with pytest.raises(PermissionError, match="liste blanche"):
        sandbox._safe_path("README.md", write_mode=True)

    # Autorisation explicite (simule le clic utilisateur côté worker)
    sandbox.whitelist_add("README.md")
    sandbox.write_file("README.md", "# Doc")
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# Doc"


def test_whitelist_add_keeps_protections(tmp_path):
    """whitelist_add ne permet PAS de contourner les autres protections."""
    sandbox = FileSandbox(tmp_path, checked_paths=[str(tmp_path / "src")],
                          write_protected_names={".agent_memoire.md"})

    # Hors du projet : toujours refusé
    with pytest.raises(PermissionError, match="hors du projet"):
        sandbox.whitelist_add("../evil.txt")

    # Chemin sensible : toujours refusé
    with pytest.raises(PermissionError, match="chemin sensible"):
        sandbox.whitelist_add(".env")

    # Fichier protégé en écriture (mémoire persistante) : toujours refusé
    with pytest.raises(PermissionError, match="fichier protégé"):
        sandbox.whitelist_add(".agent_memoire.md")

    # Dossier de sauvegarde : toujours refusé
    with pytest.raises(PermissionError, match="sauvegarde réservé"):
        sandbox.whitelist_add(".agent_backups/x.bak")


def test_whitelist_add_does_not_affect_existing_files(tmp_path):
    """Autoriser UN nouveau fichier ne débloque pas les fichiers existants voisins."""
    allowed = tmp_path / "src"
    allowed.mkdir()
    existing = tmp_path / "config.py"
    existing.write_text("x = 1", encoding="utf-8")
    sandbox = FileSandbox(tmp_path, checked_paths=[str(allowed)])

    sandbox.whitelist_add("README.md")

    # Le fichier existant non coché reste protégé
    with pytest.raises(PermissionError, match="liste blanche"):
        sandbox._safe_path("config.py", write_mode=True)


# ---------------------------------------------------------------------------
#  publish_report (inversion de contrôle : le système choisit le fichier)
# ---------------------------------------------------------------------------

def test_publish_report_basic(tmp_path):
    """Le rapport est écrit dans .agent_reports/<agent_id>.md avec l'en-tête
    système, et le chemin relatif est renvoyé."""
    sandbox = FileSandbox(tmp_path)
    rel = sandbox.publish_report("architect", "Mon plan détaillé.",
                                 header="<!-- entete systeme -->\n")
    assert rel == ".agent_reports/architect.md"
    target = tmp_path / ".agent_reports" / "architect.md"
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert text.startswith("<!-- entete systeme -->")
    assert "Mon plan détaillé." in text


def test_publish_report_versioning(tmp_path):
    """Une republication archive l'ancienne version dans history/ au lieu de
    la perdre."""
    sandbox = FileSandbox(tmp_path)
    sandbox.publish_report("reviewer", "Version 1")
    sandbox.publish_report("reviewer", "Version 2")

    current = (tmp_path / ".agent_reports" / "reviewer.md").read_text(encoding="utf-8")
    assert "Version 2" in current
    archives = list((tmp_path / ".agent_reports" / "history").glob("reviewer_*.md"))
    assert len(archives) == 1
    assert "Version 1" in archives[0].read_text(encoding="utf-8")


def test_publish_report_history_purge(tmp_path):
    """L'historique est purgé au-delà de REPORTS_HISTORY_KEEP versions."""
    sandbox = FileSandbox(tmp_path)
    sandbox.REPORTS_HISTORY_KEEP = 2  # surcharge d'instance pour le test
    for i in range(5):
        sandbox.publish_report("analyst", f"Version {i}")
    archives = list((tmp_path / ".agent_reports" / "history").glob("analyst_*.md"))
    assert len(archives) == 2


def test_publish_report_sanitizes_agent_id(tmp_path):
    """Un ID d'agent hostile (défense en profondeur : il vient normalement
    d'agents.json) ne peut pas sortir du dossier de rapports."""
    sandbox = FileSandbox(tmp_path)
    rel = sandbox.publish_report("../evil", "x")
    target = (tmp_path / rel).resolve()
    assert target.is_relative_to(tmp_path / ".agent_reports")
    assert not (tmp_path.parent / "evil.md").exists()


def test_reports_dir_write_protected(tmp_path):
    """Le dossier .agent_reports est lisible mais protégé en écriture via les
    outils classiques : le SEUL chemin d'écriture est publish_report."""
    sandbox = FileSandbox(tmp_path)
    rel = sandbox.publish_report("architect", "Plan")

    # Lecture autorisée (le Codeur doit pouvoir lire la spec)
    assert "Plan" in sandbox.read_file(rel)

    # Écriture / suppression / renommage refusés
    with pytest.raises(PermissionError, match="rapports"):
        sandbox.write_file(rel, "injection")
    with pytest.raises(PermissionError, match="rapports"):
        sandbox.delete_file(rel)
    with pytest.raises(PermissionError, match="rapports"):
        sandbox.rename_file(rel, "vole.md")
    # Créer un NOUVEAU fichier dans le dossier est aussi refusé
    with pytest.raises(PermissionError, match="rapports"):
        sandbox.write_file(".agent_reports/faux_rapport.md", "x")


def test_reports_dir_whitelist_add_refused(tmp_path):
    """whitelist_add ne permet PAS de débloquer le dossier de rapports."""
    sandbox = FileSandbox(tmp_path, checked_paths=[str(tmp_path / "src")])
    sandbox.publish_report("reviewer", "corrections")
    with pytest.raises(PermissionError, match="rapports"):
        sandbox.whitelist_add(".agent_reports/reviewer.md")
    with pytest.raises(PermissionError, match="rapports"):
        sandbox.whitelist_add(".agent_reports/nouveau.md")


def test_publish_report_works_with_whitelist(tmp_path):
    """publish_report fonctionne même en mode liste blanche stricte : le
    chemin est choisi par le système, pas par l'agent, donc la liste blanche
    (qui contrôle les chemins fournis par les agents) ne s'applique pas."""
    allowed = tmp_path / "src"
    allowed.mkdir()
    sandbox = FileSandbox(tmp_path, checked_paths=[str(allowed)])
    rel = sandbox.publish_report("debugger", "diagnostic")
    assert (tmp_path / rel).exists()
    # ... et la lecture du rapport reste possible
    assert "diagnostic" in sandbox.read_file(rel)


# ---------------------------------------------------------------------------
# V4.1.0 — durcissement sécurité
# ---------------------------------------------------------------------------

def test_recovery_file_is_sensitive(tmp_path):
    """.agent_recovery.json est un fichier système : inaccessible aux outils
    des agents, en lecture comme en écriture (empoisonnement de l'état de
    reprise impossible via les outils)."""
    (tmp_path / ".agent_recovery.json").write_text("{}", encoding="utf-8")
    sandbox = FileSandbox(tmp_path)
    with pytest.raises(PermissionError, match="chemin sensible"):
        sandbox._safe_path(".agent_recovery.json", write_mode=False)
    with pytest.raises(PermissionError, match="chemin sensible"):
        sandbox._safe_path(".agent_recovery.json", write_mode=True)
    with pytest.raises(PermissionError, match="chemin sensible"):
        sandbox.whitelist_add(".agent_recovery.json")


def test_self_modification_protected():
    """Sandbox pointé sur le dossier de l'application elle-même : les
    fichiers système (sandbox.py, workers.py...) sont protégés en écriture,
    mais restent lisibles."""
    import os
    app_dir = os.path.dirname(os.path.abspath(__file__))
    sandbox = FileSandbox(app_dir)
    for name in ("sandbox.py", "workers.py", "ui.py", "agents.json"):
        # lecture : OK
        sandbox._safe_path(name, write_mode=False)
        # écriture : refusée
        with pytest.raises(PermissionError, match="fichier protégé"):
            sandbox._safe_path(name, write_mode=True)


def test_no_false_positive_on_third_party_project(tmp_path):
    """Dans un projet TIERS, un fichier nommé workers.py ou main.py reste
    modifiable : la protection anti auto-modification ne s'applique que
    lorsque la racine contient le dossier de l'application."""
    (tmp_path / "workers.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "main.py").write_text("x = 1", encoding="utf-8")
    sandbox = FileSandbox(tmp_path)
    sandbox._safe_path("workers.py", write_mode=True)
    sandbox._safe_path("main.py", write_mode=True)


# ---------------------------------------------------------------------------
# V4.3.0 — régressions (corrections de la revue de code)
# ---------------------------------------------------------------------------

def test_grep_under_sensitive_ancestor(tmp_path):
    """BUG #3 : un projet rangé sous un chemin contenant un nom sensible
    (ex: .venv/mon_projet) rendait grep muet ("Aucun fichier à analyser")
    alors que read_file fonctionnait — le filtre inspectait le chemin
    ABSOLU au lieu des parties relatives à la racine."""
    project = tmp_path / ".venv" / "mon_projet"
    project.mkdir(parents=True)
    (project / "a.py").write_text("hello test\n", encoding="utf-8")
    sandbox = FileSandbox(project)
    res = sandbox.grep("test")
    assert "a.py:1" in res
    # ... et un dossier sensible INTERNE au projet reste bien exclu.
    inner = project / ".venv"
    inner.mkdir()
    (inner / "b.py").write_text("hello test\n", encoding="utf-8")
    res = sandbox.grep("test")
    assert "b.py" not in res


def test_list_dir_hides_sensitive_names(tmp_path):
    """SÉCU #10 : list_dir ne révèle plus l'existence des noms sensibles
    (cohérence avec tree)."""
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    sandbox = FileSandbox(tmp_path)
    entries = sandbox.list_dir()
    assert "app.py" in entries
    assert ".env" not in entries
    assert ".git/" not in entries and ".git" not in entries


def test_git_diff_command_is_hardened():
    """SÉCU #8 : git_diff neutralise textconv, ext-diff et le pager
    (un dépôt hostile pouvait exécuter du code via un driver textconv)."""
    argv = FileSandbox.ALLOWED_COMMANDS["git_diff"]
    assert "--no-textconv" in argv
    assert "--no-ext-diff" in argv
    assert "--no-pager" in argv


def test_run_named_command_resolves_absolute_binary(tmp_path, monkeypatch):
    """SÉCU #7 : run_named_command refuse un binaire introuvable sur le PATH
    (et donc ne laisse jamais CreateProcess chercher dans le cwd projet)."""
    import sandbox as sandbox_mod
    sb = FileSandbox(tmp_path)
    monkeypatch.setattr(sandbox_mod, "resolve_external_binary", lambda name: None)
    res = sb.run_named_command("git_diff")
    assert "ÉCHEC" in res and "introuvable" in res


def test_hardened_env_blocks_cwd_search():
    """SÉCU #7 : l'environnement durci pose NoDefaultCurrentDirectoryInExePath."""
    from sandbox import hardened_subprocess_env
    env = hardened_subprocess_env({})
    assert env.get("NoDefaultCurrentDirectoryInExePath") == "1"


def test_whitelist_tie_deny_wins(tmp_path):
    """ROBUSTESSE #17 : un chemin à la fois coché ET décoché (profondeur
    égale) est REFUSÉ en écriture (deny-wins)."""
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("x", encoding="utf-8")
    sandbox = FileSandbox(tmp_path, checked_paths=[str(d)], unchecked_paths=[str(d)])
    with pytest.raises(PermissionError, match="liste blanche"):
        sandbox._safe_path("src/a.py", write_mode=True)


def test_flexible_search_crlf_trailing_ws():
    """BUG #11 : le mode trailing_ws ne matchait jamais un fichier CRLF."""
    original = "def foo():   \r\n    return 1  \r\n"
    search = "def foo():\r\n    return 1"
    res = flexible_search(original, search, "def foo():\r\n    return 2")
    assert res["found"] and res["mode"] == "trailing_ws"
    new = original[:res["start"]] + res["replace"] + original[res["end"]:]
    assert new == "def foo():\r\n    return 2\r\n"  # aucune fin de ligne mixte


def test_flexible_search_crlf_indent_preserves_cr():
    """BUG #11 : le mode indent consommait le '\\r' final du bloc sur un
    fichier CRLF (fins de ligne mixtes après édition)."""
    original = "class A:\r\n    def f(self):\r\n        return 1\r\n"
    search = "def f(self):\r\n    return 1"
    replace = "def f(self):\r\n    return 2"
    res = flexible_search(original, search, replace)
    assert res["found"] and res["mode"] == "indent"
    new = original[:res["start"]] + res["replace"] + original[res["end"]:]
    assert new == "class A:\r\n    def f(self):\r\n        return 2\r\n"


def test_available_models_claude_id_uses_dashes():
    """BUG #6 : l'ID Anthropic utilise des tirets, pas des points."""
    from utils import AVAILABLE_MODELS
    claude_ids = [v for k, v in AVAILABLE_MODELS.items() if "claude" in v.lower()]
    assert claude_ids, "au moins un modèle Claude attendu"
    for mid in claude_ids:
        assert "." not in mid, f"ID Claude invalide (point interdit) : {mid}"


def test_get_filtered_models_by_provider():
    """ROBUSTESSE #18 : filtrage par fournisseur explicite, plus par mots
    magiques dans les noms affichés."""
    from utils import get_filtered_models
    api = get_filtered_models("api_key")
    assert "Claude Opus 4.8" in api
    assert "Gemma 4 31B (Gemini API)" in api
    assert "Gemma 4 (LM Studio Local)" not in api
    lm = get_filtered_models("lm_studio")
    assert lm == ["Gemma 4 (LM Studio Local)"]


def test_confirmation_diff_and_preview_announce_truncation():
    """SÉCU #9 : le diff/aperçu de confirmation affiche des statistiques
    complètes et annonce toute troncature en clair (anti-dissimulation),
    y compris pour write_file désormais."""
    workers = pytest.importorskip(
        "workers", reason="dépendances GUI/LLM absentes de cet environnement")
    LiveAgentWorker = workers.LiveAgentWorker
    original = "\n".join(f"ligne {i}" for i in range(200)) + "\n"
    new_text = "\n".join(f"LIGNE {i}" for i in range(200)) + "\n"
    diff_str = LiveAgentWorker._confirmation_diff(original, new_text, "x.txt")
    assert diff_str.startswith("[STATISTIQUES COMPLÈTES DU DIFF")
    assert "+200 ligne(s) ajoutée(s)" in diff_str
    assert "DIFF TRONQUÉ POUR L'AFFICHAGE" in diff_str

    preview = LiveAgentWorker._new_file_preview("\n".join(f"l{i}" for i in range(100)))
    assert preview.startswith("[CONTENU COMPLET : 100 ligne(s)")
    assert "APERÇU TRONQUÉ" in preview
    # Petit fichier : pas de troncature annoncée inutilement.
    small = LiveAgentWorker._new_file_preview("a\nb\n")
    assert "APERÇU TRONQUÉ" not in small


def test_rename_regex_marks_both_paths_stale():
    """BUG #12 : la purge d'historique reconnaît les renommages et marque
    l'ANCIEN et le NOUVEAU chemin comme obsolètes."""
    workers = pytest.importorskip(
        "workers", reason="dépendances GUI/LLM absentes de cet environnement")
    LiveAgentWorker = workers.LiveAgentWorker
    msg = ("Résultat de l'action rename_file :\n"
           "OK : fichier renommé de old/a.py vers new/b.py.\n\n"
           "Que fais-tu ensuite ? (JSON)")
    m = LiveAgentWorker._RENAME_OK_RE.match(msg)
    assert m is not None
    assert m.group(1) == "old/a.py"
    assert m.group(2) == "new/b.py"
    # ... et _EDIT_OK_RE ne le happe plus avec un faux chemin.
    assert LiveAgentWorker._EDIT_OK_RE.match(msg) is None
