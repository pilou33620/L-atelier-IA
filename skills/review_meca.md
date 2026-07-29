---
name: review_meca
description: Revue de conception 3D paramétrique (CadQuery).
---
Vérifie que le code de modélisation mécanique (CadQuery ou similaire) respecte nos directives strictes de conception paramétrique et modulaire.

Points de contrôle :
1. Paramétrisation : Aucune dimension géométrique ne doit être codée en dur ("magic numbers"). Toutes les dimensions doivent provenir de variables ou dictionnaires de configuration.
2. Robustesse : Le modèle résiste-t-il à des variations extrêmes des paramètres ? (Vérifier les interférences ou les faces qui disparaissent).
3. Modularié : Les assemblages complexes sont-ils bien découpés en sous-fonctions ou sous-composants réutilisables ?
4. Conventions : Les noms des variables reflètent-ils clairement leur rôle mécanique (ex: `epaisseur_paroi`, `diametre_percage`) ?

Signale les violations et propose le code corrigé.
