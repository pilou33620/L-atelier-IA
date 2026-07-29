---
name: audit_secu
description: Audit de sécurité critique (injections, traversal, secrets).
---
Effectue un audit de sécurité critique et impitoyable du code fourni. Cherche spécifiquement les vulnérabilités suivantes :

1. Injections (Commandes, SQL) : Les entrées utilisateurs sont-elles exécutées ou concaténées sans nettoyage ? (ex: utilisation dangereuse de `subprocess`, `os.system` ou requêtes SQL brutes).
2. Path Traversal : L'accès aux fichiers est-il sandboxé ? Un utilisateur peut-il lire/écrire en dehors du répertoire prévu ?
3. Prompt Injection : S'il s'agit d'interactions LLM, les données non fiables sont-elles bien séparées des instructions système ?
4. Fuite d'informations : La gestion des erreurs (`try/except`) expose-t-elle des informations sensibles, chemins absolus ou secrets ?

Format de réponse :
- Fichier + Ligne
- Vulnérabilité trouvée (Sévérité Haute/Moyenne/Basse)
- Vecteur d'attaque (Comment l'exploiter)
- Correction sécurisée proposée
