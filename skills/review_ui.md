---
name: review_ui
description: Revue d'interface utilisateur (Asynchronisme, Ergonomie).
---
Examine le code d'interface graphique (PyQt, Tkinter, etc.) fourni.

Points de contrôle critiques :
1. Non-blocage du Thread principal : Vérifie qu'absolument aucune opération longue (I/O, requêtes LLM, exécution d'agent) n'est exécutée dans le thread de l'UI. Elles doivent utiliser des threads séparés (ex: `QThread`, `QRunnable`) ou être asynchrones.
2. Gestion de l'état : Les boutons d'action sont-ils correctement grisés/désactivés pendant qu'une tâche est en cours ?
3. Retour visuel : L'utilisateur a-t-il un feedback clair (barre de progression, spinner, logs) de ce qui se passe en arrière-plan ?
4. Nettoyage du code : Y a-t-il des widgets non utilisés ou des styles redondants ?

Propose le code corrigé en ciblant d'abord la robustesse (pas de freeze UI), puis l'ergonomie.
