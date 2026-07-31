# ==========================================
# VERSIONING DU CODE
# Version : 4.4.1 (correction de la boucle « Réponse non-JSON » et
#   durcissement de l'extraction d'action :
#   BUG BLOQUANT —
#   1. workers.extract_action : l'assainissement des antislashs
#      (re.sub(r'\\(?![\\/bfnrtu"])', ...)) DÉTRUISAIT les chemins Windows
#      CORRECTEMENT échappés par le LLM. re.sub avançant de façon non
#      chevauchante, sur "C:\\Users" la position 0 était ignorée (lookahead
#      = '\\') puis le scan reprenait sur le SECOND antislash, dont le
#      suivant ('U') n'est pas échappable : il était doublé -> "C:\\\Users"
#      -> JSONDecodeError « Invalid \escape ». Tout run PAIR d'antislashs
#      suivi d'un caractère non échappable était cassé. Le message d'erreur
#      renvoyé au modèle lui conseillait alors de DOUBLER ses antislashs —
#      ce qu'il faisait déjà — d'où une boucle infinie « Réponse non-JSON,
#      on redemande... » sur toute racine du type C:\Users\<nom>\Documents.
#      Désormais : parsing du texte BRUT en premier, réparation seulement en
#      second recours, par RUNS et IDEMPOTENTE (_pair_orphan_backslashes) ;
#   2. workers : le message d'erreur et le prompt système orientent vers les
#      SLASHES AVANT ou un chemin RELATIF (tous deux acceptés par
#      _safe_path), ce qui supprime la classe de bugs à la source ;
#   ROBUSTESSE —
#   3. workers._find_balanced_end : le comptage d'accolades ignore désormais
#      les accolades situées DANS une chaîne JSON (un champ 'content'
#      contenant du code cassait la borne de fin du bloc) ;
#   4. workers : les blocs ```json sont bornés par comptage d'accolades et
#      non par le ``` fermant (survit à un ``` imbriqué dans le contenu) ;
#   5. workers : la réponse brute est JOURNALISÉE en cas d'échec de parsing
#      (le débogage était totalement aveugle) ; une réponse VIDE ou un objet
#      JSON NON TERMINÉ sont diagnostiqués comme des TRONCATURES et non
#      comme un simple « pas de JSON » ;
#   6. llm.py : max_tokens Claude passé de 8192 (codé en dur) à 32000,
#      surchargeable par ANTHROPIC_MAX_TOKENS ; stop_reason est désormais
#      lu après le stream et une troncature est signalée explicitement ;
#   SÉCURITÉ —
#   7. llm.py : le base_url Claude pointait INCONDITIONNELLEMENT vers une
#      passerelle tierce (aiprimetech.io) alors que le changelog V4.3.0
#      annonçait la suppression de ce routage. Il est maintenant matérialisé
#      par une constante nommée, JOURNALISÉ à chaque initialisation (clé API,
#      prompts et code source lu par les agents transitent par ce tiers) et
#      surchargeable par ANTHROPIC_BASE_URL, dont la valeur "official" force
#      l'API officielle d'Anthropic.)
# Version précédente : 4.4.0 (revue de code complète — crashs inter-modes, pipeline
#   Hardware et durcissement sécurité :
#   BUGS CRITIQUES —
#   1. ui.py : combo_generalist n'existe qu'en mode Assistant Général ;
#      « 🧪 Tester » (tous modes) et « 🧠 Analyse Graphify » (mode Codeur)
#      crashaient en AttributeError en modes Codeur/Hardware. Nouveau helper
#      _general_model_name() avec repli sur le modèle par défaut ;
#   2. ui.py : « 📂 Ouvrir un dossier » et 🧹 crashaient en mode Général
#      (agents_layout / chat_view inexistants) — helpers de chat résilients
#      (_main_chat_widget) + garde dans populate_agents ;
#   3. ui.py : la reprise de session ♻️ plantait dès que le journal était
#      non vide (_esc appelé sur des paires [agent, résumé] issues du JSON) ;
#   4. ui_hardware.py : « Voir les composants » générait un script à '\n'
#      LITTÉRAL (une seule ligne -> SyntaxError systématique) ; terme
#      désormais passé par repr() (anti-injection d'apostrophes) ;
#   5. convertisseur PDF-Json.py : écrivait 'datasheet/<x>/<x>.json' alors
#      que l'Agent Composant est borné à 'data_sheets/' À PLAT — le pipeline
#      Hardware ne trouvait jamais les datasheets importées. Harmonisé sur
#      'data_sheets/<x>.json' + chemins d'images relatifs à la racine projet ;
#   SÉCURITÉ —
#   6. sandbox.py : download_mcp_kicad_part — le MPN (fourni par le LLM)
#      était injecté tel quel dans le nom de fichier SANS passer par
#      _safe_path (traversée de chemin '../..' possible hors de kicad_libs/
#      voire hors projet). MPN assaini (comme publish_report) + confinement
#      re-vérifié ;
#   7. sandbox.py : '.agent_last_mission.json' rejoint les noms sensibles :
#      relu par l'UI et réinjecté comme mission au clic 🔄, il offrait un
#      vecteur de persistance d'injection identique à celui bouché pour
#      .agent_recovery.json en V4.0.1 ;
#   8. ui.py + llm.py : le fichier de clé API était PARTAGÉ entre les modes
#      Google et Claude (la clé partait vers le mauvais fournisseur en
#      alternant les modes). Réglage QSettings distinct par mode + préfixe
#      'sk-ant-' exigé avant tout appel Anthropic ;
#   9. ui_hardware.py : confirmation explicite avant l'exécution des scripts
#      SKiDL (même classe de risque que le pytest retiré en V4.0.x) ;
#      libellés PCBParts (serveur distant) affichés en texte brut (QLabel
#      interprétait le rich text) ;
#   ROBUSTESSE —
#   10. workers.py : compteurs usage_metadata potentiellement None en
#       streaming -> TypeError qui faisait échouer TOUTE la mission pour un
#       affichage de coût ; désormais gardés ;
#   11. UI : Graphify (300 s), scripts SKiDL (60 s) et recherche PCBParts
#       (30 s) tournaient sur le thread principal (interface figée) —
#       nouveau FunctionWorker générique (workers.py) ; timeouts ajoutés aux
#       subprocess de show_html_graph (aucun auparavant) ;
#   12. ui.py : imghdr (supprimé de la stdlib en Python 3.13) remplacé par
#       QImageReader ; closeEvent attend plus longtemps et inclut les
#       nouveaux workers (terminate en dernier recours) ; filtre *.bmp
#       retiré des dialogues d'images (non supporté par l'API Anthropic) ;
#   13. ui.py : liste blanche — aucune case cochée NI décochée = liste
#       blanche désactivée, conformément au texte d'aide (une liste vide
#       l'activait avec zéro chemin autorisé) ;
#   14. llm.py : garde-fou de contexte + avertissement images pour la
#       branche LM Studio ; rate limiter local pour Anthropic (40 RPM) ;
#       fallback response_mime_type restreint (la condition '400' seule
#       réinterprétait n'importe quelle erreur 400) ; cause précise affichée
#       quand le client Anthropic est indisponible (paquet manquant vs clé
#       invalide) ;
#   15. workers.py : règle système « message préalable dans le chat »
#       supprimée (contradictoire avec le protocole une-action-JSON, source
#       de boucles « Réponse non-JSON ») ; recherche web pilotée par la clé
#       'enable_search' de agents.json (l'ID 'tech_lead' codé en dur
#       n'existait dans aucune config livrée) ;
#   16. agents_hardware.json : run_tests ajouté aux outils du coder_skidl ;
#       prompt du component_agent aligné sur la structure réelle de
#       data_sheets/. NB : agents_skidl.json est une config MORTE (aucun
#       chargeur ne la référence) — suppression recommandée.)
# Version précédente : 4.3.0 (corrections de bugs critiques + durcissement sécurité,
#   suite à revue de code complète :
#   BUGS CRITIQUES —
#   1. llm.py : correction du mapping des rôles pour Claude (les tours de
#      l'assistant, stockés avec le rôle 'assistant', étaient tous envoyés
#      à l'API Anthropic en rôle 'user' : conversation multi-tours fusionnée
#      en un unique bloc user) ;
#   2. llm.py : SUPPRESSION du routage silencieux des clés non 'sk-ant-'
#      vers un proxy tiers codé en dur (aiprimetech.io) — fuite de clé
#      potentielle. Endpoint alternatif possible UNIQUEMENT via opt-in
#      explicite (variable d'environnement ANTHROPIC_BASE_URL, journalisé) ;
#      la détection de la Clé 2 comme clé Claude exige le préfixe 'sk-ant-' ;
#   3. sandbox.py : grep inspecte désormais les chemins RELATIFS à la racine
#      (même correctif que _safe_path) — un projet rangé sous un chemin
#      contenant un nom sensible (ex: ~/.venv/mon_projet) rendait grep muet ;
#   4. ui.py : suppression des 5 branches mortes 'auth_mode == "claude"'
#      (widget claude_api_key_input inexistant -> AttributeError garantie) ;
#   5. llm.py : rate limiter — les limites de Gemini PRO (4 RPM / 18 RPD)
#      étaient appliquées à TOUS les Flash ; Pro / Flash / Flash-Lite sont
#      désormais distingués ;
#   6. utils.py : ID de modèle Claude corrigé ('claude-opus-4-8', tirets) ;
#   SÉCURITÉ —
#   7. binaires externes (graphify, git) : chemin ABSOLU résolu via le PATH
#      de l'application (jamais le cwd projet) + env durci
#      NoDefaultCurrentDirectoryInExePath — anti-hijack sous Windows par un
#      exécutable homonyme déposé dans un dépôt hostile ;
#   8. git_diff : ajout de --no-textconv --no-ext-diff --no-pager (un dépôt
#      hostile pouvait exécuter du code via un driver textconv de
#      .git/config, même classe de risque que le pytest retiré en V4.0.x) ;
#   9. write_file : la confirmation humaine affiche désormais le DIFF complet
#      (fichier existant) ou un aperçu du contenu (nouveau fichier), avec
#      statistiques intégrales et troncature annoncée — fin de l'approbation
#      aveugle ; ajout du re-contrôle TOCTOU (comme edit_file) ;
#   10. list_dir masque les noms sensibles (cohérence avec tree) ;
#   ROBUSTESSE —
#   11. utils.flexible_search : support des fins de ligne CRLF (le mode
#       trailing_ws ne matchait jamais un fichier \r\n ; le mode indent
#       mangeait le \r final -> fins de ligne mixtes) ;
#   12. workers : regex dédiée aux renommages dans la purge d'historique
#       (les fichiers renommés n'étaient jamais marqués obsolètes) ;
#   13. ui.closeEvent : le worker d'Analyse Graphify est annulé lui aussi ;
#   14. llm.stream : force_json documenté et température abaissée (0.2) pour
#       les agents JSON sur Claude ; 15. estimation de tokens : forfait par
#       image (les images étaient ignorées par _fit_to_context) ;
#   16. limites quotidiennes locales classées fatales (pas de retry inutile) ;
#   17. sandbox : à profondeur égale coché/décoché, le refus l'emporte ;
#   18. utils : filtrage des modèles par FOURNISSEUR explicite
#       (MODEL_PROVIDERS) au lieu de mots magiques dans les noms affichés ;
#   19. titre de fenêtre synchronisé (V3.8 -> V4.3.0), en-tête publish_report
#       assaini ('-->').)
# Version précédente : 4.2.0 (refonte du pipeline Graphify — voir
#   l'historique git pour le détail des versions 4.2.0 / 4.1.0)
# Date : 2026-07-17
# ==========================================

import sys
import logging
try:
    import onnxruntime
except ImportError:
    pass

from PyQt6.QtWidgets import QApplication, QDialog

from ui import DARK_QSS, ConnectionDialog, MainWindow

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("[LOG - SYSTEM] Lancement de 'L'Atelier IA V4.4.1'")
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)

    while True:
        dialog = ConnectionDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_auth_mode, selected_app_mode, is_demo = dialog.get_selection()
            
            # Load appropriate config
            from core.utils import load_agents_config
            load_agents_config(selected_app_mode)
            
            window = MainWindow(auth_mode=selected_auth_mode, app_mode=selected_app_mode, is_demo=is_demo)
            window.show()
            app.exec()
            
            # Si l'utilisateur a cliqué sur "Retour" pour changer de mode de connexion
            if hasattr(window, 'wants_to_go_back') and window.wants_to_go_back:
                continue
            else:
                break
        else:
            break

    sys.exit(0)
