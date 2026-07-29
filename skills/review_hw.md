---
name: review_hw
description: Revue méthodologique électronique (KiCad, IPC, ERC/DRC).
---
Analyse les choix de composants, scripts ou structures liés au projet matériel (KiCad).

Vérifie la conformité aux standards professionnels :
1. Bibliothèques Atomiques : Chaque composant doit avoir son symbole, son empreinte (footprint) et son modèle 3D strictement associés. Pas de composants génériques.
2. Empreintes : Vérifie que le nommage des empreintes respecte les conventions IPC.
3. Intégrité : Rappelle ou vérifie les règles critiques pour réussir les tests ERC (Electrical Rules Check) et DRC (Design Rules Check) automatisés.
4. Références : Les références (U1, R1, C1) sont-elles logiques et correctement annotées ?

Fournis un rapport d'anomalies et les recommandations pour sécuriser la fabrication de la carte.
