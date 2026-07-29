---
description: Revue de code ciblée sur les problèmes réels
---
Fais la revue des changements git récents (`git diff` ou le diff de la PR courante).

Concentre-toi uniquement sur ce qui compte, dans cet ordre :
1. Bugs et erreurs de logique (null deref, cas limites, off-by-one)
2. Fuites de données sensibles (clés API, mots de passe, identifiants en dur, tokens, secrets exposés)
3. Failles de sécurité (injection SQL, auth manquante, vulnérabilités XSS/CSRF)
4. Validation des entrées (sanitisation des saisies externes et retours d'API)
5. Gestion des erreurs et logs (try/catch vides, crashs silencieux, messages d'erreur exposant des détails internes)
6. Problèmes de performance (I/O inutiles, calculs dupliqués, N+1)
7. Asynchronisme et Concurrence (I/O bloquants, await manquants, race conditions)
8. Architecture, Maintenabilité et SOLID (duplication, couplage fort, responsabilités multiples)
9. Typage et Documentation (type hints ou docstrings manquants sur le nouveau code)
10. Couverture de tests (logique complexe ou bugs corrigés sans tests unitaires)
11. Gestion des ressources (fichiers non fermés, connexions BDD non libérées, fuites mémoire)
12. Rétrocompatibilité (cassure d'API existante, migration BDD manquante)
13. Sécurité des dépendances (nouvelles bibliothèques inutiles ou risquées)
14. Violations des conventions du projet (voir AGENTS.md, .cursorrules ou autres fichiers de règles si présents)

Ignore le style et le nitpicking. Pour chaque problème :
- Fichier + numéro de ligne
- Sévérité : 🔴 Important / 🟡 À corriger / ⚪ Suggestion
- Correction proposée concise

Termine par un verdict : ✅ Prêt à merger / ⚠️ Problèmes trouvés.

⚠️ TRÈS IMPORTANT : Tu dois IMPÉRATIVEMENT formater ta réponse finale en utilisant ton outil d'action JSON (ex: `publish_report` ou `finish`). Place toute ta revue textuelle à l'intérieur de l'argument approprié (ex: "content" ou "summary"). Ne réponds AUCUN texte brut en dehors du bloc JSON, sinon le système plantera.
