import os
import time
import logging
import lmstudio as lms
from google import genai
from google.genai import types
from core.utils import get_thinking_config, is_gemma_model, get_key_slot, get_context_limit
import threading
from collections import deque

logger = logging.getLogger(__name__)


def _normalize_lm_host(url):
    """Le SDK lmstudio attend un 'host:port' SANS schéma (il construit lui-même
    ws://{host}/... et http://{host}/...). On nettoie donc l'URL saisie."""
    if not url:
        return None
    host = url.strip()
    for prefix in ("http://", "https://", "ws://", "wss://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host.rstrip("/") or None


def _init_anthropic_client(api_key):
    """Initialise le client pour OneProvider (compatible Anthropic)."""
    from anthropic import Anthropic

    key = (api_key or "").strip()
    if not key:
        return None

    return Anthropic(api_key=key, base_url="https://aiprimetech.io")


def _is_quota_error(message):
    """Vrai si l'erreur est un problème de crédits/quota JOURNALIER ou de
    facturation : inutile de retenter, il faut le signaler immédiatement.

    BUGFIX : l'ancienne version matchait le mot 'quota' seul, or les erreurs
    429 *par minute* de l'API Gemini contiennent littéralement
    "You exceeded your current quota" avec un quotaId '...PerMinute...'.
    Elles étaient donc classées fatales et le backoff exponentiel ne servait
    jamais. On ne considère désormais comme fatal que ce qui pointe vers un
    quota journalier ou un problème de crédits."""
    msg = (message or "").lower()
    # Quota par minute -> transitoire, le retry/backoff s'en charge.
    per_minute = ("per minute", "perminute", "per-minute", "requests per min")
    if any(k in msg for k in per_minute):
        return False
    fatal = ("credit", "prepayment", "billing", "per day", "perday", "per-day",
             "daily limit", "free-models-per-day", "insufficient",
             # V4.3.0 : libellés FRANÇAIS levés par notre propre RateLimiter
             # (limite quotidienne locale) — à classer fatals eux aussi.
             "limite quotidienne", "quotidien")
    return any(k in msg for k in fatal)


def _is_rate_or_quota_error(message):
    """Vrai pour toute erreur de type quota/limite (fatale OU transitoire).
    Sert notamment à détecter le refus du grounding Google Search sur le
    Free Tier, quel que soit le libellé exact du quota."""
    msg = (message or "").lower()
    keywords = ("quota", "429", "resource_exhausted", "rate limit",
                "exceeded your")
    return any(k in msg for k in keywords) or _is_quota_error(msg)


def _current_date_fr():
    """Date du jour en français, injectée dans le prompt système pour que le
    modèle ne se fie pas à sa date d'entraînement (sinon il croit être en
    2024/2025 et refuse de répondre sur des événements récents)."""
    from datetime import datetime
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]
    now = datetime.now()
    return f"{jours[now.weekday()]} {now.day} {mois[now.month - 1]} {now.year}"


def _cancellable_sleep(seconds, is_cancelled_callback=None):
    """Attente interruptible. Renvoie True si l'annulation a été demandée."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if is_cancelled_callback and is_cancelled_callback():
            return True
        time.sleep(min(0.2, max(0.0, deadline - time.time())))
    return bool(is_cancelled_callback and is_cancelled_callback())


def _estimate_tokens(text):
    """Estimation grossière : ~4 caractères par token. Suffisant comme
    garde-fou, la vraie tokenisation est côté serveur."""
    return len(text or "") // 4


# Forfait de tokens estimé PAR IMAGE jointe à un message (~1M pixels après
# redimensionnement côté API). BUGFIX (V4.3.0) : les images étaient ignorées
# par l'estimation — une mission riche en captures d'écran pouvait dépasser
# la fenêtre de contexte malgré l'élagage de _fit_to_context.
IMAGE_TOKEN_ESTIMATE = 1600


def _estimate_message_tokens(m):
    """Tokens estimés d'un message : texte (~4 car/token) + forfait par image."""
    total = _estimate_tokens(m.get("content", ""))
    total += IMAGE_TOKEN_ESTIMATE * len(m.get("images") or [])
    return total


def _fit_to_context(system_prompt, messages, model_name, output_reserve=8192):
    """Garde-fou fenêtre de contexte (ex : Gemma 4 31B = 256K tokens).

    Si l'historique estimé dépasse ~85 % de la fenêtre du modèle (marge pour
    l'imprécision de l'estimation) moins une réserve pour la réponse, on
    retire les messages les PLUS ANCIENS en préservant :
      - le 1er message (il contient la mission originale / le contexte de tâche),
      - les messages les plus récents (le travail en cours).
    Renvoie (messages_élagués, nb_retirés, limite). Ne modifie pas la liste
    d'origine. Si rien à faire : renvoie la liste telle quelle et 0.
    """
    limit = get_context_limit(model_name)
    budget = int(limit * 0.85) - output_reserve
    total = _estimate_tokens(system_prompt)
    total += sum(_estimate_message_tokens(m) for m in messages)
    if total <= budget or len(messages) <= 2:
        return messages, 0, limit

    msgs = [dict(m) for m in messages]
    removed = 0
    # On retire à partir de l'index 1 (le 0 = mission) tant qu'on dépasse.
    while total > budget and len(msgs) > 2:
        dropped = msgs.pop(1)
        total -= _estimate_message_tokens(dropped)
        removed += 1

    if removed:
        note = (f"[NOTE SYSTÈME : {removed} ancien(s) message(s) ont été retirés "
                f"de l'historique pour respecter la fenêtre de contexte du modèle "
                f"({limit:,} tokens). L'historique ci-dessous est donc partiel : "
                f"si une information te manque, relis les fichiers concernés.]\n\n")
        # BUGFIX : après élagage, msgs[1] peut être un message 'assistant' ;
        # y préfixer la note revenait à la mettre dans la bouche du modèle.
        # On l'attache donc au PREMIER message 'user' après la mission
        # (index 0), et s'il n'y en a aucun, on insère un vrai message user.
        target_idx = next((i for i in range(1, len(msgs))
                           if msgs[i].get("role") == "user"), None)
        if target_idx is not None:
            msgs[target_idx]["content"] = note + msgs[target_idx].get("content", "")
        else:
            msgs.insert(1, {"role": "user", "content": note.strip()})
    return msgs, removed, limit


class RateLimiter:
    """Limite les requêtes par minute (RPM), tokens par minute (TPM) et par jour (RPD)."""
    def __init__(self, rpm, tpm=None, rpd=None):
        self.rpm = rpm
        self.tpm = tpm
        self.rpd = rpd
        self.request_timestamps = deque()
        self.daily_request_timestamps = deque()
        self.token_timestamps = deque()
        self.lock = threading.Lock()
        
    def try_acquire(self, estimated_tokens=0):
        with self.lock:
            now = time.time()
            
            # Nettoyage
            while self.request_timestamps and now - self.request_timestamps[0] > 60:
                self.request_timestamps.popleft()
            while self.daily_request_timestamps and now - self.daily_request_timestamps[0] > 86400:
                self.daily_request_timestamps.popleft()
            if self.tpm:
                while self.token_timestamps and now - self.token_timestamps[0][0] > 60:
                    self.token_timestamps.popleft()
            
            sleep_time = 0
            if self.rpd and len(self.daily_request_timestamps) >= self.rpd:
                # NB (V4.3.0) : ce libellé contient 'limite quotidienne',
                # reconnu comme FATAL par _is_quota_error (pas de retry inutile).
                raise Exception(f"Limite quotidienne atteinte (RPD: {self.rpd}). Réessayez demain.")
                
            if self.rpm and len(self.request_timestamps) >= self.rpm:
                sleep_time = max(sleep_time, 60 - (now - self.request_timestamps[0]))
                
            if self.tpm and estimated_tokens > 0:
                estimated_tokens = min(estimated_tokens, self.tpm)
                current_tokens = sum(t for _, t in self.token_timestamps)
                if current_tokens + estimated_tokens > self.tpm:
                    freed = 0
                    for ts, toks in self.token_timestamps:
                        freed += toks
                        if current_tokens - freed + estimated_tokens <= self.tpm:
                            sleep_time = max(sleep_time, 60 - (now - ts))
                            break
            
            if sleep_time <= 0:
                self.request_timestamps.append(now)
                self.daily_request_timestamps.append(now)
                if self.tpm and estimated_tokens > 0:
                    self.token_timestamps.append((now, estimated_tokens))
                return 0
            return sleep_time

class GlobalRateLimiter:
    _limiters = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_limiter(cls, model_name, key_slot=1):
        """Un limiteur par couple (clé API, modèle) : deux clés = deux quotas
        indépendants côté Google, donc deux compteurs indépendants ici."""
        with cls._lock:
            cache_key = (key_slot, model_name)
            if cache_key not in cls._limiters:
                name_lower = model_name.lower()
                if "claude" in name_lower:
                    # V4.4.0 : la branche Anthropic ne reposait QUE sur le
                    # retry 429 — une mission multi-agents enchaînait les
                    # backoffs. Limite prudente (Tier 1 Anthropic : 50 RPM) ;
                    # pas de RPD local, Anthropic n'a pas de quota journalier
                    # en requêtes.
                    cls._limiters[cache_key] = RateLimiter(rpm=40, tpm=None, rpd=None)
                    return cls._limiters[cache_key]
                if key_slot == 2:
                    # Clé n°2 = forfait PAYANT (Tier 1) : limites bien plus
                    # hautes. On reste volontairement en dessous des plafonds
                    # officiels (~150 RPM / 2M TPM / 1000+ RPD sur Gemini Pro)
                    # pour garder une marge de sécurité.
                    rpm = 100
                    tpm = 1_500_000
                    rpd = 900
                else:
                    # Clé n°1 = forfait GRATUIT : limites prudentes.
                    # BUGFIX (V4.3.0) : l'ancien code appliquait les limites
                    # de Gemini PRO (4 RPM / 18 RPD) à TOUS les modèles dont
                    # le nom contient 'flash' — une mission multi-agents sur
                    # Flash mourait après ~18 requêtes ("Limite quotidienne
                    # atteinte"). Pro, Flash et Flash-Lite sont désormais
                    # distingués, avec des valeurs volontairement en dessous
                    # des plafonds officiels du Free Tier.
                    rpm, tpm, rpd = 14, None, 1450
                    if "pro" in name_lower:
                        rpm, tpm, rpd = 4, 200_000, 18
                    elif "flash-lite" in name_lower:
                        rpm, tpm, rpd = 14, 250_000, 1000
                    elif "flash" in name_lower:
                        rpm, tpm, rpd = 9, 250_000, 250
                    elif "gemma" in name_lower:
                        rpm, tpm, rpd = 14, None, 1450
                cls._limiters[cache_key] = RateLimiter(rpm, tpm, rpd)
            return cls._limiters[cache_key]


class LLMProvider:
    def __init__(self, auth_mode, api_key=None, lm_url=None, api_key_2=None, api_key_claude=None):
        self.auth_mode = auth_mode
        self.api_key = api_key
        self.api_key_2 = api_key_2
        self.api_key_claude = api_key_claude
        self.lm_url = lm_url
        self.client = None
        # Clients Google indexés par numéro de clé (1 = défaut, 2 = optionnelle).
        self.clients = {}
        self.anthropic_client = None

        if self.auth_mode == "lm_studio":
            # BUGFIX : lms.Client n'a PAS de paramètre 'base_url'.
            # Sa signature est Client(api_host) et l'hôte doit être sans schéma.
            host = _normalize_lm_host(self.lm_url)
            self.client = lms.Client(host) if host else lms.Client()
        elif self.auth_mode in ("api_key", "google_claude"):
            self.client = genai.Client(api_key=self.api_key)
            self.clients[1] = self.client
            if api_key_2 and api_key_2 != self.api_key:
                self.clients[2] = genai.Client(api_key=api_key_2)
            self.anthropic_error = None
            if self.auth_mode == "google_claude" and self.api_key_claude:
                try:
                    self.anthropic_client = _init_anthropic_client(self.api_key_claude)
                    if self.anthropic_client is None:
                        self.anthropic_error = "La clé Claude semble invalide ou 'anthropic' n'est pas installé."
                except Exception as e:
                    self.anthropic_client = None
                    self.anthropic_error = f"Erreur init Anthropic : {e}"
        elif self.auth_mode == "claude":
            self.api_key_claude = self.api_key
            # BUGFIX (V4.4.0) : l'ImportError était avalée en silence -> le
            # message ultérieur « Clé API Claude manquante » était trompeur
            # quand le vrai problème était l'absence du paquet 'anthropic'.
            # On mémorise la cause pour l'afficher à l'utilisateur.
            self.anthropic_error = None
            try:
                self.anthropic_client = _init_anthropic_client(self.api_key_claude)
                if self.anthropic_client is None:
                    self.anthropic_error = "clé absente ou invalide"
            except ImportError:
                self.anthropic_client = None
                self.anthropic_error = ("paquet Python 'anthropic' non installé "
                                        "(pip install anthropic)")
        else:
            raise ValueError(f"Mode de connexion inconnu : {auth_mode}")

    # ------------------------------------------------------------------ #
    #  Routage multi-clés                                                 #
    # ------------------------------------------------------------------ #
    def _key_slot_for(self, model_name):
        """Numéro de clé effectivement utilisé pour ce modèle.
        Retombe sur la clé 1 si la clé 2 n'est pas configurée."""
        if self.auth_mode != "api_key":
            return 1
        slot = get_key_slot(model_name)
        return slot if slot in self.clients else 1

    def _client_for(self, model_name):
        """Client Google à utiliser pour ce modèle (routage par modèle)."""
        if self.auth_mode == "lm_studio":
            return self.client
        return self.clients.get(self._key_slot_for(model_name), self.client)

    # ------------------------------------------------------------------ #
    #  Test de connexion                                                  #
    # ------------------------------------------------------------------ #
    def test_connection(self, models_to_test):
        """Teste la connexion pour les modèles donnés. Lève une exception en cas d'erreur."""
        if self.auth_mode == "lm_studio":
            for model_name in models_to_test:
                model = self.client.llm.model(model_name)
                model.respond("Test de connexion. Réponds juste 'OK'.")
        else:  # Google GenAI (api_key)
            for i, model_name in enumerate(models_to_test):
                if i > 0:
                    # BUGFIX : sans pause, tester plusieurs modèles à la suite
                    # déclenchait le quota par minute (429) -> faux négatif.
                    time.sleep(2)
                real_model_name, _ = get_thinking_config(model_name)
                
                if "claude" in real_model_name.lower():
                    if not getattr(self, 'anthropic_client', None):
                        raise Exception(f"Clé Claude manquante pour tester {model_name}.")
                    self.anthropic_client.messages.create(
                        model=real_model_name,
                        max_tokens=10,
                        messages=[{"role": "user", "content": "Test de connexion. Réponds juste 'OK'."}]
                    )
                    continue

                key_slot = self._key_slot_for(real_model_name)
                client = self._client_for(real_model_name)

                limiter = GlobalRateLimiter.get_limiter(real_model_name, key_slot)
                while True:
                    wait_time = limiter.try_acquire(10)
                    if wait_time <= 0:
                        break
                    time.sleep(wait_time)

                max_retries = 5
                retry_delay = 5
                for attempt in range(max_retries):
                    try:
                        client.models.generate_content(
                            model=real_model_name,
                            contents="Test de connexion. Réponds juste 'OK'."
                        )
                        break
                    except Exception as e:
                        err_str = str(e)
                        # Crédits épuisés : inutile de retenter.
                        if _is_quota_error(err_str):
                            raise
                        # BUGFIX : retry sur 429/500/503 pour le test Google.
                        # Le 500 "Internal error" est fréquent et transitoire
                        # sur les endpoints Gemma notamment.
                        if (any(code in err_str for code in ("429", "500", "503"))
                                and attempt < max_retries - 1):
                            time.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 40)
                        else:
                            raise

    # ------------------------------------------------------------------ #
    #  Streaming                                                          #
    # ------------------------------------------------------------------ #
    def stream(self, system_prompt, messages, model_name, is_cancelled_callback=None,
               enable_search=False, force_json=False):
        """
        Générateur qui yield des tuples (type_message, contenu).
        type_message: "chunk" (texte généré), "status" (message informatif pour l'UI).
        enable_search : active le grounding Google Search (modèles Gemini via
        l'API Google uniquement ; ignoré pour Gemma et LM Studio qui ne le
        supportent pas).
        force_json : active le mode "sortie JSON structurée" de l'API Gemini
        (response_mime_type). Le modèle est alors contraint par l'API de
        produire du JSON valide, ce qui élimine quasiment toutes les réponses
        non parsables des agents. Ignoré pour LM Studio et Gemma (non
        supporté), et incompatible avec le grounding Google Search (l'API
        refuse la combinaison outils + JSON mode) : dans ce cas la recherche
        est prioritaire et on retombe sur le parsing texte classique.
        NB Claude (API Anthropic) : il n'existe pas d'équivalent API à
        response_mime_type ; force_json abaisse la température (0.2 au lieu
        de 0.7) pour fiabiliser le JSON, et extract_action (workers.py)
        reste le filet de sécurité. enable_search est ignoré pour Claude.
        """
        # Injection de la date du jour : sans elle, les modèles se croient à
        # leur date d'entraînement et répondent faux sur tout ce qui est récent.
        system_prompt = (f"Information contextuelle : nous sommes le {_current_date_fr()}.\n\n"
                         + (system_prompt or ""))

        if self.auth_mode == "lm_studio":
            # BUGFIX (V4.4.0) : le garde-fou de fenêtre de contexte n'était
            # appliqué qu'à la branche Google/Anthropic — une longue mission
            # locale finissait en erreur côté serveur LM Studio.
            messages, removed_count, ctx_limit = _fit_to_context(
                system_prompt, messages, model_name)
            if removed_count:
                yield "status", (f"\n[🧹 Contexte presque plein ({ctx_limit:,} tokens max "
                                 f"pour ce modèle) : {removed_count} ancien(s) message(s) "
                                 f"retirés de l'historique.]\n")
            # V4.4.0 : les images jointes étaient silencieusement perdues en
            # mode local — l'utilisateur est désormais prévenu.
            if any(m.get("images") for m in messages):
                yield "status", ("\n[ℹ️ Les images jointes sont ignorées en mode "
                                 "LM Studio (non supporté par ce connecteur).]\n")
            model = self.client.llm.model(model_name)
            chat = lms.Chat(system_prompt)
            for msg in messages:
                if msg["role"] == "user":
                    chat.add_user_message(msg["content"])
                elif msg["role"] == "assistant":
                    chat.add_assistant_message(msg["content"])
            for fragment in model.respond_stream(chat):
                if is_cancelled_callback and is_cancelled_callback():
                    return
                if fragment.content:
                    yield "chunk", fragment.content

        else:  # Google GenAI / Anthropic
            real_model_name, config_params = get_thinking_config(model_name)
            is_gemma = is_gemma_model(real_model_name)

            # Garde-fou fenêtre de contexte : appliqué AVANT le branchement
            # par provider, donc valable aussi pour Claude (200K tokens :
            # BUGFIX, l'ancienne version ne l'appliquait qu'aux modèles
            # Google, et une longue mission sur Claude finissait en 400).
            messages, removed_count, ctx_limit = _fit_to_context(
                system_prompt, messages, real_model_name)
            if removed_count:
                yield "status", (f"\n[🧹 Contexte presque plein ({ctx_limit:,} tokens max "
                                 f"pour ce modèle) : {removed_count} ancien(s) message(s) "
                                 f"retirés de l'historique.]\n")

            if "claude" in real_model_name.lower():
                if not getattr(self, 'anthropic_client', None):
                    # V4.4.0 : cause précise (clé invalide vs paquet manquant).
                    cause = getattr(self, 'anthropic_error', None) or "clé API Claude manquante"
                    yield "status", f"\n[❌ Claude indisponible : {cause}.]\n"
                    return
                anthropic_messages = []
                for msg in messages:
                    # BUGFIX CRITIQUE (V4.3.0) : l'historique stocke les
                    # réponses du modèle avec le rôle 'assistant' (workers.py,
                    # ui.py), jamais 'model'. L'ancien test (== "model")
                    # classait donc TOUS les tours de l'assistant en 'user' :
                    # la conversation multi-tours arrivait à l'API Anthropic
                    # fusionnée en un unique bloc user géant (structure de
                    # dialogue détruite dès le 2e tour).
                    role = "assistant" if msg["role"] in ("assistant", "model") else "user"
                    anthropic_content = [{"type": "text", "text": msg["content"]}]
                    if "images" in msg and msg["images"]:
                        import base64
                        import mimetypes
                        import os
                        for img_path in msg["images"]:
                            if os.path.exists(img_path):
                                mime_type, _ = mimetypes.guess_type(img_path)
                                if not mime_type: mime_type = "image/jpeg"
                                try:
                                    with open(img_path, "rb") as f:
                                        data = base64.b64encode(f.read()).decode("utf-8")
                                    anthropic_content.append({
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": mime_type,
                                            "data": data
                                        }
                                    })
                                except Exception as e:
                                    print(f"Error loading image {img_path}: {e}")
                    if anthropic_messages and anthropic_messages[-1]["role"] == role:
                        anthropic_messages[-1]["content"].extend(anthropic_content)
                    else:
                        anthropic_messages.append({"role": role, "content": anthropic_content})
                
                # V4.4.0 : limiteur local (RPM) pour Anthropic aussi — la
                # branche ne reposait que sur le retry 429.
                estimated_tokens = len(system_prompt) // 4
                for msg in messages:
                    estimated_tokens += _estimate_message_tokens(msg)
                limiter = GlobalRateLimiter.get_limiter(real_model_name, 1)
                while True:
                    wait_time = limiter.try_acquire(estimated_tokens)
                    if wait_time <= 0:
                        break
                    yield "status", (f"\n[⏳ Sécurité anti-limite : attente "
                                     f"{wait_time:.1f}s pour respecter le quota...]\n")
                    if _cancellable_sleep(wait_time, is_cancelled_callback):
                        return

                # Retry avec backoff sur les erreurs transitoires (même
                # logique que la branche Google) : 429 = rate limit,
                # 500/503/529 = surcharge côté Anthropic. On ne retente
                # JAMAIS si du texte a déjà été émis (réponse partielle).
                max_retries = 5
                retry_delay = 5
                attempt = 0
                while True:
                    has_yielded = False
                    try:
                        logger.info(f"Appel API OneProvider avec le modèle : {real_model_name}")
                        with self.anthropic_client.messages.stream(
                            model=real_model_name,
                            max_tokens=8192,
                            system=system_prompt,
                            messages=anthropic_messages,
                            # V4.3.0 : force_json n'a pas d'équivalent côté
                            # Anthropic -> température abaissée pour les
                            # agents JSON (extract_action reste le filet).
                            temperature=0.2 if force_json else 0.7
                        ) as stream_ctx:
                            for text in stream_ctx.text_stream:
                                if is_cancelled_callback and is_cancelled_callback():
                                    return
                                if text:
                                    yield "chunk", text
                                    has_yielded = True
                        return
                    except Exception as e:
                        if has_yielded:
                            raise e
                        err_str = str(e)
                        # Crédits/quota épuisés : inutile de retenter.
                        if _is_quota_error(err_str):
                            raise e
                        attempt += 1
                        if (any(code in err_str for code in ("429", "500", "503", "529", "overloaded"))
                                and attempt < max_retries):
                            yield "status", (f"\n[⚠️ Erreur temporaire côté Anthropic, "
                                             f"nouvelle tentative dans {retry_delay}s...]\n")
                            if _cancellable_sleep(retry_delay, is_cancelled_callback):
                                return
                            retry_delay = min(retry_delay * 2, 40)
                        else:
                            raise e

            # Routage multi-clés : chaque modèle est servi par la clé API qui
            # lui est assignée (utils.MODELS_ON_KEY_2). Fallback clé 1 sinon.
            key_slot = self._key_slot_for(real_model_name)
            client = self._client_for(real_model_name)
            if key_slot == 2:
                yield "status", "\n[🔑 Ce modèle utilise la Clé API n°2 (forfait payant).]\n"

            # Les modèles Gemma via l'API Gemini n'acceptent PAS le paramètre
            # 'system_instruction' (erreur HTTP 400 "Developer instruction is
            # not enabled"). On injecte donc le prompt système dans le premier
            # message utilisateur à la place.
            if not is_gemma:
                config_params["system_instruction"] = system_prompt
                # Grounding Google Search : réservé aux modèles Gemini.
                if enable_search:
                    config_params["tools"] = [types.Tool(google_search=types.GoogleSearch())]
                elif force_json:
                    # Mode JSON structuré : l'API garantit une sortie JSON
                    # syntaxiquement valide. Exclusif avec 'tools' (voir docstring).
                    config_params["response_mime_type"] = "application/json"

            contents = []
            system_injected = not is_gemma or not system_prompt
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                text = msg["content"]
                if not system_injected and role == "user":
                    text = (f"[INSTRUCTIONS SYSTÈME]\n{system_prompt}\n"
                            f"[/INSTRUCTIONS SYSTÈME]\n\n{text}")
                    system_injected = True
                
                parts = [types.Part.from_text(text=text)]
                
                if "images" in msg and msg["images"]:
                    import mimetypes
                    import os
                    for img_path in msg["images"]:
                        if os.path.exists(img_path):
                            mime_type, _ = mimetypes.guess_type(img_path)
                            if not mime_type: mime_type = "image/jpeg"
                            try:
                                with open(img_path, "rb") as f:
                                    data = f.read()
                                parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
                            except Exception as e:
                                print(f"Error loading image {img_path}: {e}")
                
                if contents and contents[-1].role == role:
                    contents[-1].parts.extend(parts)
                else:
                    contents.append(types.Content(role=role, parts=parts))
            if not system_injected:
                # Cas limite : aucun message 'user' dans l'historique.
                contents.insert(0, types.Content(
                    role="user",
                    parts=[types.Part.from_text(
                        text=f"[INSTRUCTIONS SYSTÈME]\n{system_prompt}\n[/INSTRUCTIONS SYSTÈME]")]
                ))

            # BUGFIX : l'ancienne boucle 'for attempt in range(...)' pouvait se
            # terminer sans 'break' ni 'raise' (cas du fallback sans outil de
            # recherche survenant à la dernière tentative) -> le stream
            # s'arrêtait en silence. On utilise un 'while' explicite : chaque
            # sortie est soit un succès (return), soit une exception levée.
            max_retries = 5
            retry_delay = 5
            attempt = 0
            
            estimated_tokens = len(system_prompt) // 4
            for msg in messages:
                # V4.3.0 : les images comptent aussi (forfait par image).
                estimated_tokens += _estimate_message_tokens(msg)
                
            limiter = GlobalRateLimiter.get_limiter(real_model_name, key_slot)
            while True:
                wait_time = limiter.try_acquire(estimated_tokens)
                if wait_time <= 0:
                    break
                yield "status", f"\n[⏳ Sécurité anti-limite : attente {wait_time:.1f}s pour respecter le quota...]\n"
                if _cancellable_sleep(wait_time, is_cancelled_callback):
                    return

            while True:
                has_yielded = False
                try:
                    response = client.models.generate_content_stream(
                        model=real_model_name, contents=contents,
                        config=types.GenerateContentConfig(**config_params),
                    )
                    for chunk in response:
                        if is_cancelled_callback and is_cancelled_callback():
                            return
                        if chunk.text:
                            yield "chunk", chunk.text
                            has_yielded = True
                        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                            yield "usage", chunk.usage_metadata
                    return
                except Exception as e:
                    if has_yielded:
                        raise e
                    err_str = str(e)
                    # Cas particulier : le grounding Google Search est refusé
                    # pour cause de quota (le Free Tier n'y a pas droit sur
                    # certains modèles). Plutôt que d'échouer, on retente la
                    # même requête SANS l'outil de recherche. Ce fallback ne
                    # consomme PAS une tentative (il ne peut se produire
                    # qu'une seule fois puisque l'outil est retiré).
                    if _is_rate_or_quota_error(err_str) and config_params.get("tools"):
                        config_params.pop("tools", None)
                        yield "status", ("\n[ℹ️ Recherche web non incluse dans ton quota actuel "
                                         "(réservée au palier payant sur ce modèle). "
                                         "Nouvelle tentative sans recherche...]\n")
                        continue
                    # Cas particulier : certains modèles/endpoints refusent le
                    # mode JSON structuré (400 INVALID_ARGUMENT sur
                    # response_mime_type). On retente sans : le parsing texte
                    # classique (extract_action) prend le relais. Ce fallback
                    # ne consomme pas une tentative (une seule fois possible).
                    # BUGFIX (V4.4.0) : la condition incluait '400' seul —
                    # N'IMPORTE quelle erreur 400 (requête réellement invalide,
                    # contexte dépassé...) était réinterprétée comme « JSON
                    # mode non supporté » et retentée. On exige un indice
                    # spécifique au mode JSON.
                    if (config_params.get("response_mime_type")
                            and ("response_mime_type" in err_str
                                 or "INVALID_ARGUMENT" in err_str)):
                        config_params.pop("response_mime_type", None)
                        yield "status", ("\n[ℹ️ Mode JSON structuré non supporté par ce modèle, "
                                         "nouvelle tentative en mode texte...]\n")
                        continue
                    # Crédits/quota journalier épuisés : inutile de retenter.
                    if _is_quota_error(err_str):
                        raise e
                    # 429 = quota/minute, 503 = surcharge, 500 = erreur interne
                    # transitoire (fréquente sur les endpoints Gemma) : tous
                    # méritent une nouvelle tentative avec backoff.
                    attempt += 1
                    if (any(code in err_str for code in ("429", "500", "503"))
                            and attempt < max_retries):
                        yield "status", f"\n[⚠️ Erreur temporaire côté Google, nouvelle tentative dans {retry_delay}s...]\n"
                        # BUGFIX : attente interruptible (le bouton Stop répond immédiatement).
                        if _cancellable_sleep(retry_delay, is_cancelled_callback):
                            return
                        retry_delay = min(retry_delay * 2, 40)
                    else:
                        raise e
