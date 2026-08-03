# 🛠️ L'Atelier IA

**L'Atelier IA** est un environnement de développement assisté par une équipe d'agents IA autonomes. Contrairement à un simple chat, l'outil orchestre plusieurs spécialistes (Architecte, Codeur, Revieweur, etc.) capables d'explorer, de modifier et de tester du code localement dans un environnement sécurisé.

## 🚀 Fonctionnalités Principales

- **Système Multi-Agents** : Un Orchestrateur analyse vos demandes et délègue les tâches à des agents spécialisés :
    - 🏛️ **Architecte** : Conçoit la structure et les spécifications.
    - 💻 **Codeur** : Implémente la logique et corrige les bugs.
    - 🧐 **Revieweur** : Valide les changements et exige des corrections si nécessaire.
    - 🤖 **Assistant Général** : Chat classique avec accès à de vastes bases de connaissances.
    - 🔌 **Hardware Designer** : Agent spécialisé dans la conception électronique (datasheets, SKiDL).
    - ⚙️ **Concepteur 3D (Meca)** : Agent spécialisé dans la modélisation CAO (CadQuery), la génération de fichiers STEP et la prévisualisation 3D (CQ-Editor).
    - 🛠️ **Autres** : Analyste, Débogueur, Expert Sécurité, Tech Lead, etc.
- **Sandbox de Fichiers Sécurisée** : 
    - Lecture et écriture contrôlées dans un dossier projet.
    - Liste blanche d'écriture pour limiter les modifications aux fichiers choisis.
    - Sauvegardes automatiques de chaque modification dans `.agent_backups`.
    - Outil `outline_file` pour analyser la structure des gros fichiers sans saturer le contexte.
- **Compatibilité LLM étendue** : 
    - Intégration native avec **Google GenAI** (via clé API, support étendu pour Gemini 3.1 Pro et Gemini 3.6).
    - Intégration d'**Anthropic Claude** (via clé API ou Google GenAI + Claude).
    - Support de **LM Studio** pour l'exécution de modèles locaux (Gemma, etc.).
- **Interface IDE Intégrée** : 
    - Explorateur de fichiers avec gestion des permissions et notifications visuelles lors de l'accès aux fichiers.
    - Éditeur de code avec coloration syntaxique Python.
    - **Nouveau** : Autocomplétion intelligente des **Skills** dans le chat (tapez `/` pour déclencher des experts métiers : `/review`, `/audit_secu`, `/test`, `/review_meca`...).
    - Panneaux distincts pour les différents agents (Codeur, Général, Hardware, Meca).
    - Icônes et vues unifiées pour le Mode Essaim (Swarm).

## 🛠️ Installation

### Prérequis
- Python 3.10 ou supérieur

### Mise en place
1. Clonez le dépôt :
   ```bash
   git clone https://github.com/votre-nom/latelier-ia.git
   cd latelier-ia
   ```
2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Lancez l'application :
   ```bash
   python main.py
   ```

## 📖 Utilisation rapide

1. **Connexion** : Au démarrage, choisissez votre mode de connexion (**Google GenAI + Claude** ou **LM Studio**). Vous pouvez y activer le **Mode Démonstration** pour tester l'application dans un dossier sécurisé avec un modèle gratuit.
2. **Projet** : Cliquez sur "Ouvrir un dossier" pour définir la racine du projet sur laquelle l'IA va travailler (automatique en Mode Démo).
3. **Mission** : Dans l'onglet "Agent Codeur", décrivez votre objectif (ex: "Ajoute une fonction de tri dans utils.py et crée un test correspondant") ou utilisez le bouton "Démo technique".
4. **Suivi** : Suivez le raisonnement de l'Orchestrateur et les actions des agents en temps réel.
5. **Validation** : Une fois la mission terminée, consultez le bilan final et les diffs avant de valider les changements.

## 🛡️ Sécurité et Précautions
- L'outil crée un dossier `.agent_backups` à la racine du projet pour permettre la restauration de fichiers en cas d'erreur.
- Soyez vigilant quant aux fichiers sensibles (secrets, `.env`) présents dans le dossier projet, car ils peuvent être lus par l'IA et envoyés au fournisseur du modèle.