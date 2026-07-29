import os
import re
import json

AGENTS_CONFIG = {}

def load_agents_config(mode):
    global AGENTS_CONFIG
    
    if mode == 'hardware':
        sub_dir = 'hardware'
        filename = 'agents_hardware.json'
    elif mode == 'meca':
        sub_dir = 'meca'
        filename = 'agents_meca.json'
    elif mode == 'coder':
        sub_dir = 'coder'
        filename = 'agents.json'
    else:
        sub_dir = 'general'
        filename = 'agents.json'
        
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), sub_dir, filename)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            AGENTS_CONFIG.clear()
            AGENTS_CONFIG.update(json.load(f))
            
        if mode == 'meca':
            cq_path = os.path.join(os.path.dirname(config_path), 'cadquery_commands.json')
            if os.path.exists(cq_path):
                try:
                    with open(cq_path, 'r', encoding='utf-8') as cq_f:
                        cq_data = json.load(cq_f)
                        cq_text = "\n\n### RÉFÉRENCE CADQUERY (À UTILISER IMPÉRATIVEMENT) ###\n"
                        api_data = cq_data.get("cadquery_api", {})
                        cq_text += api_data.get("description", "") + "\n"
                        for cat, cmds in api_data.get("categories", {}).items():
                            cq_text += f"\nCatégorie : {cat.replace('_', ' ').title()}\n"
                            for cmd in cmds:
                                cq_text += f"- {cmd.get('commande', '')} : {cmd.get('description', '')}\n  Exemple: {cmd.get('exemple', '')}\n"
                        
                        for agent_id, agent_info in AGENTS_CONFIG.items():
                            if 'system_prompt' in agent_info and agent_id in ['designer', 'reviewer', 'tech_lead']:
                                agent_info['system_prompt'] += cq_text
                except Exception as e:
                    print(f"Erreur lors du chargement de {cq_path} : {e}")

    except Exception as e:
        print(f"Erreur lors du chargement de {config_path} : {e}")


AVAILABLE_MODELS = {
    "Gemini 3.1 Pro Preview (Standard)": "gemini-3.1-pro-preview",
    "Gemini 3.1 Pro Preview (Extended)": "gemini-3.1-pro-preview-extended",
    # "Gemini 3.6 Thinking" N'EST PAS un modèle distinct côté API : c'est
    # le même modèle que "Gemini 3.6 Flash" (ID API : gemini-3.6-flash) mais
    # avec le niveau de réflexion poussé au maximum. On distingue la variante
    # par le suffixe interne "-thinking" (retiré avant l'appel API, exactement
    # comme "-extended" pour le 3.1 Pro). Voir get_thinking_config().
    "Gemini 3.6 Thinking": "gemini-3.6-flash-thinking",
    "Gemini 3.6 Flash": "gemini-3.6-flash",
    # Modèles open-weight Gemma servis par la même API Gemini (clé AI Studio).
    "Gemma 4 31B (Gemini API)": "gemma-4-31b-it",
    "Gemma 4 26B A4B (Gemini API)": "gemma-4-26b-a4b-it",
    "Gemma 4 (LM Studio Local)": "google/gemma-4-26b-a4b-qat",
    "Claude Opus 4.8": "claude-opus-4-8[1m]",
    "Claude Fable 5": "claude-fable-5[1m]",
}

# --- Fournisseur de chaque modèle (V4.3.0) -----------------------------------
# BUGFIX/ROBUSTESSE : l'ancien filtrage par mode de connexion reposait sur la
# présence de mots magiques dans le NOM AFFICHÉ ("Gemini", "LM Studio"...) —
# fragile et non documenté. On associe désormais explicitement chaque ID de modèle
# à son fournisseur :
#   - "gemini"    : modèles Gemini (API AI Studio) ;
#   - "gemma_api" : modèles Gemma appelés via l'API Gemini ;
#   - "lm_studio" : modèles locaux via LM Studio ;
#   - "anthropic" : modèles Claude (mode api_key uniquement).
MODEL_PROVIDERS = {
    "gemini-3.1-pro-preview": "gemini",
    "gemini-3.1-pro-preview-extended": "gemini",
    "gemini-3.6-flash-thinking": "gemini",  # variante "Thinking" du 3.6 Flash
    "gemini-3.6-flash": "gemini",
    "gemma-4-31b-it": "gemma_api",
    "gemma-4-26b-a4b-it": "gemma_api",
    "google/gemma-4-26b-a4b-qat": "lm_studio",
    "claude-opus-4-8[1m]": "anthropic",
    "claude-fable-5[1m]": "anthropic",
}

def get_model_provider(display_name):
    """Fournisseur du modèle à partir de son nom AFFICHÉ."""
    return MODEL_PROVIDERS.get(AVAILABLE_MODELS.get(display_name, ""), "")

# --- Multi-clés API (mode api_key uniquement) -------------------------------
# Modèles routés vers la Clé API n°2 (ex : forfait payant / Tier 1).
# Tous les autres modèles utilisent la Clé n°1 (ex : forfait gratuit).
# Si aucune Clé 2 n'est sélectionnée dans l'interface, TOUT retombe
# automatiquement sur la Clé 1 (aucune erreur).
# NB : on liste ici les IDs de modèles (valeurs de AVAILABLE_MODELS), le
# suffixe "-extended" étant retiré avant l'appel API, on couvre les deux formes.
MODELS_ON_KEY_2 = {
    "gemini-3.1-pro-preview",
    "gemini-3.1-pro-preview-extended",
    "gemini-3.6-flash",
    "gemini-3.6-flash-thinking",
}

def get_key_slot(model_name):
    """Renvoie 1 ou 2 : le numéro de la clé API à utiliser pour ce modèle."""
    return 2 if (model_name or "") in MODELS_ON_KEY_2 else 1

# --- Fenêtres de contexte (tokens max en ENTRÉE par modèle) ------------------
# Sert de garde-fou : au-delà, l'API renvoie une erreur 400. L'outil élague
# automatiquement les plus anciens messages de l'historique pour rester sous
# la limite (voir llm.py : _fit_to_context).
MODEL_CONTEXT_LIMITS = {
    "gemma": 256_000,      # Gemma 4 31B / 26B A4B : 256K tokens
    "claude": 1_000_000,   # Claude (OneProvider) : 1M tokens
    "default": 1_000_000,  # Gemini 3.x : 1M tokens
}

def get_context_limit(model_name):
    """Fenêtre de contexte (en tokens) du modèle donné."""
    name = (model_name or "").lower()
    if "gemma" in name:
        return MODEL_CONTEXT_LIMITS["gemma"]
    if "claude" in name:
        return MODEL_CONTEXT_LIMITS["claude"]
    return MODEL_CONTEXT_LIMITS["default"]

def get_filtered_models(auth_mode):
    # V4.3.0 : filtrage par FOURNISSEUR explicite (MODEL_PROVIDERS) au lieu
    # de mots magiques dans les noms affichés.
    if auth_mode == "api_key":
        allowed = {"gemini", "gemma_api"}
    elif auth_mode == "google_claude":
        allowed = {"gemini", "gemma_api", "anthropic"}
    elif auth_mode == "claude":
        allowed = {"anthropic"}
    elif auth_mode == "lm_studio":
        allowed = {"lm_studio"}
    else:
        return list(AVAILABLE_MODELS.keys())
    return [k for k in AVAILABLE_MODELS.keys() if get_model_provider(k) in allowed]

def get_default_model(filtered_models):
    if not filtered_models:
        return ""
    default_model = filtered_models[0]
    for m in filtered_models:
        if "Gemma 4 31B" in m or "Gemma 4 (" in m:
            default_model = m
            break
    return default_model

def is_gemma_model(model_name):
    """Vrai si le modèle est un Gemma servi par l'API Gemini.
    Ces modèles n'acceptent pas le paramètre 'system_instruction' :
    le prompt système doit être injecté dans le premier message utilisateur."""
    return "gemma" in (model_name or "").lower()

def get_thinking_config(model_name):
    """Renvoie (real_model_name, config_params) pour les modèles Gemini.

    Gère deux familles à réflexion configurable :
      - 3.1 Pro : suffixe "-extended" => ThinkingLevel.HIGH, sinon MEDIUM ;
      - 3.6 Flash : suffixe "-thinking" (entrée "Gemini 3.6 Thinking" de
        l'interface) => ThinkingLevel.HIGH ; sans suffixe ("Gemini 3.6 Flash")
        on laisse le niveau par défaut du modèle (medium) en n'envoyant
        aucun thinking_config.
    Dans les deux cas le suffixe interne est retiré pour retrouver l'ID API
    réel (gemini-3.1-pro-preview / gemini-3.6-flash)."""
    from google.genai import types
    config_params = {}
    if "3.1-pro" in model_name:
        is_extended = "-extended" in model_name
        real_name = model_name.replace("-extended", "")
        level = types.ThinkingLevel.HIGH if is_extended else types.ThinkingLevel.MEDIUM
        config_params["thinking_config"] = types.ThinkingConfig(thinking_level=level)
        return real_name, config_params
    if "3.6-flash" in model_name:
        # "gemini-3.6-flash-thinking" -> ID API "gemini-3.6-flash" + HIGH.
        # "gemini-3.6-flash" simple  -> défaut du modèle (pas de override).
        is_thinking = "-thinking" in model_name
        real_name = model_name.replace("-thinking", "")
        if is_thinking:
            config_params["thinking_config"] = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.HIGH
            )
        return real_name, config_params
    return model_name, config_params

# --- Correspondance tolérante pour edit_file (search/replace) ----------------
# Le matching exact échoue souvent avec les LLM à cause d'espaces de fin de
# ligne ou d'une indentation légèrement décalée (cas observé en mission :
# le Codeur échoue sur web/index.html et doit s'y reprendre à deux fois).
# On garde le matching EXACT en priorité, puis deux fallbacks prudents :
#   1) "trailing_ws" : tolère uniquement les espaces/tabs de FIN de ligne ;
#   2) "indent"      : tolère un décalage d'indentation UNIFORME (le même
#      nombre de caractères ajoutés/retirés sur toutes les lignes non vides),
#      et réajuste le bloc 'replace' du même décalage.
# Chaque mode conserve l'exigence d'UNICITÉ du bloc dans le fichier.

def _shift_indent(text, shift):
    """Décale l'indentation de chaque ligne non vide de 'shift' caractères."""
    if shift == 0:
        return text
    out = []
    for line in text.split("\n"):
        if not line.strip():
            out.append(line)
        elif shift > 0:
            out.append(" " * shift + line)
        else:
            k = 0
            while k < -shift and k < len(line) and line[k] in " \t":
                k += 1
            out.append(line[k:])
    return "\n".join(out)

def flexible_search(original, search, replace):
    """Localise le bloc 'search' dans 'original' avec 3 niveaux de tolérance.

    Renvoie un dict :
      found       : bool
      mode        : "exact" | "trailing_ws" | "indent" | None
      occurrences : nombre d'occurrences trouvées (l'unicité est vérifiée
                    par l'appelant)
      start, end  : bornes (en caractères) de la PREMIÈRE occurrence
      replace     : bloc de remplacement, éventuellement réindenté (mode indent)
    """
    not_found = {"found": False, "mode": None, "occurrences": 0,
                 "start": -1, "end": -1, "replace": replace}
    if not search:
        return not_found

    # 1) Correspondance exacte (comportement historique)
    count = original.count(search)
    if count:
        start = original.find(search)
        return {"found": True, "mode": "exact", "occurrences": count,
                "start": start, "end": start + len(search), "replace": replace}

    # 2) Tolérance aux espaces de fin de ligne uniquement.
    #    Le début du bloc est ancré en début de ligne pour ne PAS tolérer
    #    accidentellement l'indentation de la première ligne.
    #    BUGFIX (V4.3.0) : les fins de ligne CRLF sont tolérées — l'ancien
    #    pattern ('[ \t]*' + '\n') ne matchait jamais un fichier '\r\n'.
    #    Le '\r?' est placé ENTRE les lignes uniquement : le '\r' final de
    #    la DERNIÈRE ligne n'est pas consommé, sinon le remplacement
    #    produisait des fins de ligne mixtes (perte du '\r' terminal).
    search_lines = search.split("\n")
    line_patterns = [re.escape(l.rstrip()) + r"[ \t]*" for l in search_lines]
    pattern = "(?:^|(?<=\n))" + r"\r?\n".join(line_patterns)
    try:
        matches = list(re.finditer(pattern, original))
    except re.error:
        matches = []
    if matches:
        m0 = matches[0]
        return {"found": True, "mode": "trailing_ws", "occurrences": len(matches),
                "start": m0.start(), "end": m0.end(), "replace": replace}

    # 3) Tolérance à un décalage d'indentation UNIFORME (lignes comparées
    #    après rstrip ; le décalage doit être identique sur toutes les
    #    lignes non vides du bloc).
    o_lines = original.split("\n")
    s_lines = search_lines
    m = len(s_lines)
    found = []
    for i in range(len(o_lines) - m + 1):
        shift = None
        ok = True
        for j in range(m):
            s = s_lines[j].rstrip()
            o = o_lines[i + j].rstrip()
            if not s and not o:
                continue
            ss, oo = s.lstrip(), o.lstrip()
            if ss != oo:
                ok = False
                break
            d = (len(o) - len(oo)) - (len(s) - len(ss))
            if shift is None:
                shift = d
            elif d != shift:
                ok = False
                break
        if ok and shift is not None:
            found.append((i, shift))
    if found:
        i, shift = found[0]
        start = sum(len(l) + 1 for l in o_lines[:i])
        end = start + sum(len(o_lines[i + j]) + 1 for j in range(m)) - 1
        # BUGFIX (V4.3.0) : sur un fichier CRLF, les lignes issues de
        # split("\n") se terminent par '\r' ; sans ce correctif, le '\r'
        # final du bloc était consommé par le remplacement (fins de ligne
        # mixtes dans le fichier résultant).
        if o_lines[i + m - 1].endswith("\r"):
            end -= 1
        return {"found": True, "mode": "indent", "occurrences": len(found),
                "start": start, "end": end,
                "replace": _shift_indent(replace, shift)}

    return not_found

def fetch_url_text(url):
    """Télécharge et nettoie le texte d'une page Web."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return "ERREUR: Les modules 'requests' et 'beautifulsoup4' ne sont pas installés."
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Supprimer les balises indésirables
        for script in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            script.extract()
            
        text = soup.get_text(separator=' ', strip=True)
        # Limiter pour ne pas saturer le LLM
        return text[:15000]
    except Exception as e:
        return f"ERREUR lors de la lecture de l'URL : {e}"