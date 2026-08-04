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

## 📂 Arborescence du Projet

L'architecture du projet est organisée de la manière suivante :

```text
L'atelier IA/
├── main.py : Point d'entrée principal de l'application lançant l'interface utilisateur.
├── ui.py : Interface utilisateur principale de l'IDE orchestrant les différentes vues.
├── ui_coder.py : Module de l'interface spécifique à l'onglet de l'agent codeur.
├── ui_general.py : Module de l'interface pour le chat avec l'assistant général.
├── ui_hardware.py : Module de l'interface dédié à l'agent de conception électronique (Hardware).
├── ui_meca.py : Module de l'interface gérant l'agent de conception mécanique 3D (Meca).
├── requirements.txt : Liste des dépendances et bibliothèques Python nécessaires au projet.
├── README.md : Documentation principale de présentation du projet (ce fichier).
├── MANUEL.md : Manuel d'utilisation détaillé des différentes fonctionnalités de l'outil.
├── CHANGELOG.md : Historique des modifications, mises à jour et correctifs du projet.
├── core/ : Moteur principal de l'application (LLM, orchestration, outils).
│   ├── llm.py : Gestion des connexions et interactions avec les modèles de langage (API et local).
│   ├── nodal_graph.py : Gestionnaire du graphe nodal pour l'exécution d'agents en mode Graphify.
│   ├── nodal_graph_original.py : Version originale de sauvegarde du système de graphe nodal.
│   ├── rag_engine.py : Moteur de RAG (Retrieval-Augmented Generation) pour la recherche documentaire.
│   ├── sandbox.py : Environnement sécurisé contrôlant les opérations de lecture/écriture sur les fichiers.
│   ├── utils.py : Fonctions utilitaires transverses utilisées à travers l'application.
│   └── workers.py : Définition des tâches asynchrones pour éviter de bloquer l'interface graphique.
├── coder/ : Configuration des agents logiciels.
│   └── agents.json : Définition des rôles, outils et prompts de l'équipe de développement.
├── general/ : Configuration de l'assistant général.
│   └── agents.json : Paramètres et prompt de l'assistant IA généraliste.
├── hardware/ : Outils et agents pour la conception électronique.
│   ├── agents_hardware.json : Configuration des agents spécialisés dans le design hardware.
│   ├── agents_skidl.json : Configuration de l'agent dédié à la génération de schémas avec SKiDL.
│   └── convertisseur PDF-Json.py : Script utilitaire pour extraire les données de datasheets PDF.
├── meca/ : Outils et agents pour la conception mécanique 3D.
│   ├── agents_meca.json : Configuration des agents en charge de la modélisation CAO.
│   └── cadquery_commands.json : Base de données des commandes CadQuery pour l'agent mécanicien.
├── skills/ : Base de compétences métier (déclenchables avec / dans le chat).
│   ├── audit_secu.md : Instructions de l'expert pour l'audit de sécurité du code.
│   ├── materials_selection.md : Compétence pour l'aide au choix des matériaux en mécanique.
│   ├── refactor.md : Instructions pour le refactoring et l'optimisation du code.
│   ├── review.md : Skill générique pour la revue de code logiciel.
│   ├── review_hw.md : Skill pour la vérification technique des conceptions électroniques.
│   ├── review_meca.md : Skill pour l'analyse des modèles CAO et contraintes physiques.
│   ├── review_ui.md : Compétence dédiée à l'évaluation des interfaces utilisateur.
│   └── test.md : Instructions pour la conception et validation de tests unitaires.
└── tests/ : Suite de tests unitaires du projet.
    ├── test_llm.py : Tests validant la communication avec les modèles de langage.
    ├── test_nodal_graph.py : Tests vérifiant la bonne exécution des graphes nodaux.
    ├── test_rag_engine.py : Tests pour le moteur de recherche et d'indexation documentaire.
    ├── test_sandbox.py : Tests assurant la robustesse et la sécurité de la sandbox.
    ├── test_utils.py : Tests des fonctions utilitaires diverses.
    └── test_workers.py : Tests des processus parallèles et tâches d'arrière-plan.
```

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