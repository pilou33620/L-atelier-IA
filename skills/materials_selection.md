---
name: materials_selection
description: Méthodologie de sélection de matériaux pour pièces mécaniques (impression 3D et usinage CNC).
---

# Sélection de Matériaux pour Conception Mécanique

## Étapes de sélection

1. **Identifier les contraintes critiques** : Température, résistance mécanique, environnement
2. **Filtrer les matériaux incompatibles** : Éliminer ceux qui ne respectent pas les critères bloquants
3. **Évaluer les matériaux restants** : Système de scoring multi-critères
4. **Recommander le TOP 3** : Avec justification et compromis

## Critères d'évaluation

### Thermique
- Température de service continue (°C)
- Température de déformation sous charge (HDT)
- Conductivité thermique (W/m·K)
- Coefficient de dilatation thermique (µm/m·°C)

### Mécanique
- Résistance à la traction (MPa)
- Module d'élasticité (GPa)
- Allongement à la rupture (%)
- Résistance aux chocs (Izod/Charpy)
- Dureté (Shore/Rockwell)

### Environnement
- Résistance UV
- Résistance à l'humidité
- Résistance chimique (acides, bases, solvants)
- Tenue en extérieur

### Fabrication
- Facilité d'impression 3D (support, warping, adhérence)
- Usinabilité (vitesse de coupe, outils)
- Tolérance dimensionnelle atteignable
- Post-traitement requis

## Tableau comparatif des matériaux FDM

| Matériau | Temp. service | Résistance chocs | UV | Humidité | Coût relatif | Difficulté impression |
|----------|--------------|-----------------|-----|----------|-------------|----------------------|
| PLA | 50-60°C | Faible | Mauvaise | Mauvaise | € | Facile |
| ABS | 80-100°C | Bonne | Moyenne | Moyenne | € | Moyen |
| PETG | 70-80°C | Moyenne | Moyenne | Bonne | €€ | Facile |
| Nylon PA | 80-120°C | Très bonne | Moyenne | Mauvaise* | €€ | Difficile |
| TPU | 60-80°C | Excellente | Moyenne | Bonne | €€ | Moyen |
| PC | 110-130°C | Excellente | Bonne | Moyenne | €€€ | Difficile |
| ASA | 90-100°C | Bonne | Excellente | Bonne | €€ | Moyen |
| PP | 80-100°C | Bonne | Moyenne | Excellente | €€ | Difficile |

*Le Nylon est hygroscopique : il absorbe l'humidité et doit être stocké au sec.

## Matériaux par application

### Applications haute température (>80°C)
- **Impression 3D FDM** : Nylon PA, PC, ASA
- **Impression 3D SLA** : Résine haute température (HDT jusqu'à 200°C)
- **Impression 3D SLS** : Nylon PA12
- **Usinage CNC** : Aluminium 6061/7075, PEEK

### Applications flexibles / amortissement des vibrations
- **Impression 3D FDM** : TPU, TPE
- **Impression 3D SLA** : Résine flexible
- **Usinage / Moulage** : Polyuréthane, Silicone

### Applications haute résistance mécanique
- **Impression 3D FDM** : PC, Nylon PA
- **Impression 3D SLS** : Nylon PA12, TPU SLS
- **Impression 3D SLA** : Résine renforcée (ABS-like)
- **Usinage CNC** : Acier inox 304/316, Aluminium 7075, PEEK

### Applications extérieures / résistance UV
- **Impression 3D FDM** : ASA (recommandé), PETG (limité), PC
- **Usinage CNC** : Aluminium anodisé, Acier inox

### Applications contact alimentaire
- **Impression 3D FDM** : PETG (certifié), PP
- **Usinage CNC** : Acier inox 304/316, PP
- ⚠️ PLA non recommandé (porosité, dégradation)

### Applications résistance chimique
- **Impression 3D FDM** : PP (acides/bases), PETG (solvants légers)
- **Usinage CNC** : Acier inox 316 (chlorures), PEEK (solvants forts), UHMW

### Applications haute précision (tolérances < ±0.1mm)
- **Impression 3D SLA** : Résine standard ou ABS-like
- **Usinage CNC** : Aluminium, Acier, Delrin/POM
- ⚠️ FDM limité à ±0.2mm, SLA à ±0.05mm, CNC à ±0.01mm

## Signaux d'alerte

- 🔴 **Cahier des charges incomplet** → Demander précisions à l'utilisateur
- 🔴 **Contraintes contradictoires** → Proposer compromis ou assemblage multi-matériaux
- 🟠 **Température > 150°C** → Impression 3D FDM très limitée, privilégier SLA haute température ou usinage CNC
- 🟠 **Tolérances < ±0.1mm** → Privilégier usinage CNC ou SLA, FDM insuffisant
- 🟠 **Nylon + humidité élevée** → Traitement de surface ou changement de matériau requis
- 🟠 **Budget très limité + haute performance** → Compromis inévitable, proposer alternative
- 🟡 **ABS en espace confiné** → Vapeurs toxiques, ventilation obligatoire
- 🟡 **PLA extérieur** → Dégradation UV et thermique rapide, déconseillé

## Paramètres d'impression recommandés

### FDM - Températures de buse typiques
| Matériau | Buse (°C) | Lit (°C) | Enceinte |
|----------|-----------|----------|----------|
| PLA | 190-220 | 50-60 | Non requise |
| ABS | 230-250 | 100-110 | Recommandée |
| PETG | 230-250 | 70-90 | Optionnelle |
| Nylon PA | 240-270 | 70-90 | Recommandée |
| TPU | 220-240 | 30-60 | Non requise |
| PC | 270-300 | 100-120 | Obligatoire |
| ASA | 240-260 | 90-110 | Recommandée |

### Orientations d'impression (FDM)
- **Pièces en traction** : Orienter les couches perpendiculairement à la force
- **Pièces en flexion** : Orienter les couches dans le sens de la flexion
- **Pièces étanches** : Augmenter le périmètre (≥4périmètres) et l'infill (≥50%)
- **Pièces filetées** : Axe du filetage parallèle à l'axe Z
