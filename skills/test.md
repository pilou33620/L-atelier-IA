---
name: test
description: Génération de tests unitaires rigoureux avec gestion des cas limites.
---
Analyse le code fourni et génère des tests unitaires robustes.

Consignes strictes :
1. Utilise le framework de test standard (ex: `pytest` ou `unittest`).
2. Couvre les cas nominaux (fonctionnement normal).
3. Teste impérativement les cas limites (edge cases) : valeurs nulles, vides, types inattendus.
4. Utilise des mocks (`unittest.mock.patch` ou pytest-mock) pour toutes les dépendances externes, les accès fichiers système, les bases de données ou les appels réseau.
5. Structure les tests de manière claire (Arrange, Act, Assert).

Fournis le code des tests prêt à être exécuté.
