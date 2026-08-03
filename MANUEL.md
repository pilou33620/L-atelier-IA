# 📘 Manuel d'Utilisation — L'Atelier IA

Bienvenue dans le manuel de L'Atelier IA. Ce guide vous explique comment configurer et utiliser l'outil pour transformer vos idées en code fonctionnel grâce à une équipe d'agents IA spécialisés.

---

## 1. ⚙️ Configuration et Démarrage

### Installation
1. Assurez-vous d'avoir Python 3.10+ installé.
2. Clonez le projet depuis GitHub :
   ```bash
   git clone https://github.com/votre-nom/latelier-ia.git
   cd latelier-ia
   ```
3. Installez les dépendances via le terminal :
   ```bash
   pip install -r requirements.txt
   ```
4. Lancez l'application :
   ```bash
   python main.py
   ```

### Choix de la Connexion
Au lancement, une fenêtre vous demande comment vous souhaitez connecter l'IA :
- **🔑 Google GenAI + Claude** : Utilise une clé API AI Studio (et optionnellement une clé Claude). Vous pouvez configurer deux clés : une principale (gratuite) et une secondaire (payante/Tier 1) pour les modèles plus puissants comme Gemini 3.1 Pro et Gemini 3.6.
- **🖥️ LM Studio** : Connexion à un serveur local. Vous devez avoir LM Studio lancé avec le serveur HTTP activé (généralement sur `http://127.0.0.1:1234`).

### Mode Démonstration
Pour découvrir les capacités de L'Atelier IA sans impacter vos projets :
- Cochez **"🧪 Activer le Mode Démonstration (Dossier temporaire, Gemma 31B)"** dans le menu de démarrage.
- L'application créera un environnement de test sécurisé (dossier temporaire) et forcera l'utilisation du modèle gratuit `Gemma 4 31B`.
- Une fois connecté, un bouton **"🧪 Démo technique"** apparaîtra en bas du chat pour lancer automatiquement un cas d'usage typique, avec ou sans le "Mode Essaim".

---

## 2. 📂 Gestion du Projet

### Sélection du Dossier
L'IA ne peut travailler que dans un dossier spécifique pour éviter de modifier des fichiers système. 
- Cliquez sur **"Ouvrir un dossier"** ou **"Sélectionner un dossier..."**.
- Une fois sélectionné, l'explorateur de fichiers affiche l'arborescence du projet.

### Le Système de Sandbox (Sécurité)
Pour protéger vos données, l'outil utilise un système de "Sandbox" :
- **Lecture** : L'IA peut lire tous les fichiers du projet (sauf dossiers sensibles comme `.git` ou `.venv`).
- **Écriture (Liste Blanche)** : 
    - Par défaut, si aucune case n'est cochée dans l'explorateur, l'IA peut modifier tout le projet.
    - **Si vous cochez des fichiers/dossiers**, l'IA ne pourra écrire QUE dans ces éléments. C'est une sécurité cruciale pour éviter que l'IA ne modifie des fichiers critiques par erreur.
- **Sauvegardes** : Chaque modification effectuée par l'IA crée une copie de sauvegarde dans le dossier `.agent_backups`. Vous pouvez ainsi revenir en arrière si une modification est insatisfaisante.

---

## 3. 🤖 Travailler avec l'Agent Codeur

L'onglet **"Agent Codeur"** est le cœur de l'outil. Ce n'est pas un simple chat, mais un système d'orchestration.

### Comment lancer une mission
1. **Décrivez votre besoin** dans la zone de saisie (ex: *"Ajoute une gestion d'erreurs dans la fonction de connexion et crée un test unitaire pour vérifier le cas d'échec"*).
2. **L'Orchestrateur** prend la main : il analyse la demande et délègue le travail :
    - 🏛️ **Architecte** $ightarrow$ définit le plan.
    - 💻 **Codeur** $ightarrow$ écrit le code.
    - 🧐 **Revieweur** $ightarrow$ vérifie que tout est correct et lance les tests.

### Options de Mission
- **Auto-Approve (Auto-validation)** : Si activé, l'IA n'attend pas votre accord pour chaque lecture/écriture de fichier. **Attention** : la commande `run_tests` (pytest) demandera TOUJOURS votre confirmation car elle exécute du code sur votre machine.
- **Règles Supplémentaires** : Vous pouvez ajouter des consignes strictes (ex: *"Utilise uniquement des fonctions asynchrones"*) pour guider tous les agents.
- **Notifications Visuelles** : L'interface affiche désormais des alertes (popups) en temps réel lorsque les agents lisent des fichiers locaux, permettant de suivre leurs accès.

### Bilan Final et Restauration
À la fin d'une mission, l'outil affiche un résumé et les **Diffs** (différences entre l'ancien et le nouveau code).
- Si le résultat ne vous convient pas, vous pouvez cliquer sur **"Restaurer les fichiers"** pour annuler tous les changements de la mission en un clic.

---

## 4. 💬 L'Assistant Général

L'onglet **"Assistant Général"** est un chat classique. Il est utile pour :
- Poser des questions théoriques sur le code.
- Demander des explications sur un algorithme.
- Faire des recherches web (pour les modèles Gemini) grâce au mode Grounding.

Il n'a pas accès aux outils de modification de fichiers, il est là pour vous conseiller.

---

## 5. 🔌 Le Hardware Designer

L'onglet **"Hardware Designer"** est dédié à la conception de circuits électroniques. Ses fonctionnalités clés incluent :
- **Analyse de Datasheets** : Import automatisé et conversion de datasheets PDF en JSON (via PyMuPDF) avec extraction et analyse visuelle (Vision). Le système organise automatiquement ces données dans un dossier `data_sheets`.
- **Conception SKiDL** : Intégration de SKiDL avec respect des règles de conception strictes (Golden Rules) pour la définition des composants, le routage d'alimentation, et le routage des signaux.
- **Archivage et Calculs** : Accès à une base de formules électroniques au format JSON pour assister l'agent dans ses calculs.
- **Simulation d'empilement** : Intégration avec les données d'empilement (stackup) issues des designs IPC2581 pour la simulation et l'analyse.

---

## 6. ⚙️ L'Agent Concepteur 3D (Meca)

L'onglet **"Agent Concepteur 3D"** permet d'interagir avec des agents spécialisés dans la CAO mécanique :
- **Modélisation CadQuery** : Génération de scripts CadQuery robustes pour la modélisation paramétrique 3D (fichiers `.py` et `.step`).
- **Base de commandes vérifiées** : Utilisation d'un dictionnaire de commandes CadQuery validées (`cadquery_commands.json`) pour garantir la précision géométrique.
- **Intégration CQ-Editor** : Visualisation directe des modèles générés ou de fichiers STEP grâce au bouton "👁️ Voir dans CQ-Editor".

---

## 7. 💡 Astuces pour de meilleurs résultats

- **Soyez précis** : Au lieu de dire *"Corrige le bug"*, dites *"L'erreur IndexError survient à la ligne 42 de main.py quand la liste est vide, corrige-le"*.
- **Utilisez l'Architecte** : Pour les grosses fonctionnalités, demandez explicitement un plan d'architecture avant l'implémentation.
- **Surveillez le journal** : Le flux de texte vous montre quel agent travaille. Si l'Orchestrateur boucle, n'hésitez pas à interrompre la mission et à reformuler votre demande.
- **Nettoyage** : Pensez à supprimer périodiquement le dossier `.agent_backups` s'il devient trop volumineux.

---

## 8. 🛠️ Commandes Rapides (Skills)

L'Atelier IA supporte des raccourcis sous forme de "slash commands" pour appliquer des comportements spécifiques (skills). Tapez `/` dans la barre de saisie pour afficher l'autocomplétion.

Voici les skills disponibles :
- **`/audit_secu`** : Audit de sécurité critique (injections, traversal, secrets).
- **`/refactor`** : Refactorisation du code pour améliorer la lisibilité (SOLID, DRY).
- **`/review`** : Revue de code ciblée sur les problèmes réels.
- **`/review_hw`** : Revue méthodologique électronique (KiCad, IPC, ERC/DRC).
- **`/review_meca`** : Revue de conception 3D paramétrique (CadQuery).
- **`/review_ui`** : Revue d'interface utilisateur (Asynchronisme, Ergonomie).
- **`/test`** : Génération de tests unitaires rigoureux avec gestion des cas limites.