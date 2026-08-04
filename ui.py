import os
import sys
import re
import math
import html
import stat
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTextEdit, QComboBox, QPushButton, QFileDialog, QMessageBox,
                             QFrame, QSplitter, QTreeView, QPlainTextEdit, QCheckBox,
                             QScrollArea, QTabWidget, QLineEdit, QApplication,
                             QDialog, QRadioButton, QDialogButtonBox, QInputDialog, QButtonGroup, QMenu, QListWidget, QProgressBar)
from PyQt6.QtCore import Qt, QTimer, QSettings, QFileSystemWatcher, pyqtSignal, QRectF
from PyQt6.QtGui import QFileSystemModel, QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QPainter, QPainterPath, QPen, QBrush, QAction

from core.sandbox import FileSandbox, resolve_external_binary, hardened_subprocess_env
from core.workers import (TestKeyWorker, SimpleChatWorker, LiveAgentWorker,
                          GraphifyAnalysisWorker, FunctionWorker)
from core.utils import AGENTS_CONFIG, AVAILABLE_MODELS, get_filtered_models, get_default_model
from core.nodal_graph import NodeGraphWidget
import logging

logger = logging.getLogger(__name__)

def resolve_slash_command(text):
    text = text.strip()
    if not text.startswith("/"):
        return text

    prompts_dir = os.path.join(os.path.dirname(__file__), "skills")
    resolved_contents = []

    while text.startswith("/"):
        parts = text.split(maxsplit=1)
        command = parts[0][1:]
        cmd_file = os.path.join(prompts_dir, f"{command}.md")

        if os.path.exists(cmd_file):
            try:
                with open(cmd_file, "r", encoding="utf-8") as f:
                    resolved_contents.append(f.read())
            except Exception as e:
                logger.error(f"Erreur chargement commande {command}: {e}")
                break
            
            text = parts[1].strip() if len(parts) > 1 else ""
        else:
            break

    if resolved_contents:
        if text:
            resolved_contents.append(f"Arguments fournis :\n{text}")
        return "\n\n".join(resolved_contents)

    return text

DARK_QSS = """
QWidget { background:#1e1e1e; color:#d4d4d4; font-family:'Segoe UI',Arial; font-size:13px; }
QMainWindow, QDialog { background:#1e1e1e; }
QFrame#Toolbar { background:#2d2d30; border-bottom:1px solid #3c3c3c; }
QFrame#EditorHead, QFrame#InputRow { background:#252526; border-bottom:1px solid #3c3c3c; }
QFrame#Sep { background:#3c3c3c; max-width:1px; margin:2px 4px; }
QLabel#PanelHeader { background:#2d2d30; color:#bbbbbb; font-weight:bold; padding:6px; letter-spacing:1px; }
QLabel#Muted { color:#858585; font-size:11px; padding:2px 4px; }
QPushButton { background:#3a3d41; color:#e0e0e0; border:1px solid #4a4a4a; border-radius:5px; padding:5px 10px; }
QPushButton:hover { background:#45494e; }
QPushButton:disabled { background:#2a2a2a; color:#666666; }
QPushButton#Accent { background:#0e639c; border:1px solid #0e639c; color:white; font-weight:bold; }
QPushButton#Accent:hover { background:#1177bb; }
QComboBox { background:#3c3c3c; border:1px solid #4a4a4a; border-radius:4px; padding:3px 6px; min-width:120px; }
QComboBox QAbstractItemView { background:#252526; selection-background-color:#0e639c; }
QLineEdit, QTextEdit, QPlainTextEdit { background:#1e1e1e; color:#d4d4d4; border:1px solid #3c3c3c; border-radius:4px; }
QTreeView { background:#252526; border:none; outline:0; }
QTreeView::item { padding:3px; }
QTreeView::item:hover { background:#2a2d2e; }
QTreeView::item:selected { background:#094771; }
QPlainTextEdit#Editor { background:#1e1e1e; border:none; padding:6px; }
QTextEdit#Chat { background:#1e1e1e; border:none; padding:8px; }
QTextEdit#ChatInput { background:#2d2d30; border:1px solid #3c3c3c; border-radius:6px; padding:4px; }
QScrollBar:vertical { background:#1e1e1e; width:12px; }
QScrollBar::handle:vertical { background:#424242; border-radius:5px; min-height:24px; }
QScrollBar::handle:vertical:hover { background:#4f4f4f; }
QScrollBar::add-line, QScrollBar::sub-line { height:0; }
QHeaderView::section { background:#252526; color:#bbbbbb; border:none; }
QRadioButton, QCheckBox { padding:4px; }
QRadioButton::indicator { width: 14px; height: 14px; border: 1px solid #858585; border-radius: 8px; background: #252526; }
QRadioButton::indicator:hover { border-color: #0e639c; }
QRadioButton::indicator:checked { border: 1px solid #0e639c; background: #0e639c; image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='14' height='14'><circle cx='12' cy='12' r='6' fill='white'/></svg>"); }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #858585; border-radius: 3px; background: #252526; }
QCheckBox::indicator:hover { border-color: #0e639c; }
QCheckBox::indicator:checked { border: 1px solid #0e639c; background: #0e639c; image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='14' height='14'><path fill='white' d='M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>"); }
QTabWidget::pane { border: 1px solid #3c3c3c; background: #1e1e1e; }
QTabBar::tab { background: #2d2d30; color: #d4d4d4; padding: 6px 12px; border: 1px solid #3c3c3c; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
QTabBar::tab:selected { background: #1e1e1e; border-top: 2px solid #0e639c; color: #ffffff; }
QTabBar::tab:hover:!selected { background: #3a3d41; }
"""

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        kw_fmt = QTextCharFormat(); kw_fmt.setForeground(QColor("#569cd6"))
        keywords = ["def", "class", "return", "if", "elif", "else", "for", "while",
                    "import", "from", "as", "try", "except", "finally", "with",
                    "lambda", "None", "True", "False", "and", "or", "not", "in",
                    "is", "pass", "break", "continue", "raise", "yield", "global",
                    "nonlocal", "assert", "del", "async", "await", "self"]
        for kw in keywords:
            self.rules.append((re.compile(r"\b" + kw + r"\b"), kw_fmt))

        num_fmt = QTextCharFormat(); num_fmt.setForeground(QColor("#b5cea8"))
        self.rules.append((re.compile(r"\b[0-9]+\.?[0-9]*\b"), num_fmt))

        def_fmt = QTextCharFormat(); def_fmt.setForeground(QColor("#dcdcaa"))
        self.rules.append((re.compile(r"(?<=def )\w+"), def_fmt))
        self.rules.append((re.compile(r"(?<=class )\w+"), def_fmt))

        # Chaînes et commentaires en dernier pour qu'ils l'emportent
        str_fmt = QTextCharFormat(); str_fmt.setForeground(QColor("#ce9178"))
        self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self.rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        com_fmt = QTextCharFormat(); com_fmt.setForeground(QColor("#6a9955"))
        self.rules.append((re.compile(r"#[^\n]*"), com_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

class ChatInputWidget(QTextEdit):
    returnPressed = pyqtSignal()
    imagePasted = pyqtSignal(object)  # QImage
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.completer_list = QListWidget()
        self.completer_list.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.completer_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.completer_list.setStyleSheet("""
            QListWidget { background: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; border-radius: 4px; }
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected { background: #0e639c; color: white; }
        """)
        self.completer_list.hide()
        self.completer_list.itemClicked.connect(self.insert_completion)
        self.textChanged.connect(self.check_completion)
        
        self.skills = []
        try:
            import os
            prompts_dir = os.path.join(os.path.dirname(__file__), "skills")
            if os.path.exists(prompts_dir):
                for file in os.listdir(prompts_dir):
                    if file.endswith(".md"):
                        self.skills.append(f"/{file[:-3]}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error loading skills for autocomplete: {e}")
            
    def check_completion(self):
        text = self.toPlainText()
        cursor = self.textCursor()
        text_before_cursor = text[:cursor.position()]
        
        last_space_idx = max(text_before_cursor.rfind(' '), text_before_cursor.rfind('\n'))
        word = text_before_cursor[last_space_idx + 1:]
        
        if word.startswith("/") and not text_before_cursor.endswith(" ") and not text_before_cursor.endswith("\n"):
            matches = [s for s in self.skills if s.startswith(word)]
            if matches:
                self.completer_list.clear()
                self.completer_list.addItems(matches)
                
                rect = self.cursorRect(cursor)
                pt = self.mapToGlobal(rect.bottomRight())
                pt.setY(pt.y() + 5)
                self.completer_list.move(pt)
                self.completer_list.resize(250, min(200, self.completer_list.sizeHintForRow(0) * len(matches) + 10))
                self.completer_list.show()
                self.completer_list.setCurrentRow(0)
                return
                
        self.completer_list.hide()
        
    def insert_completion(self, item):
        cursor = self.textCursor()
        text = self.toPlainText()
        cursor_pos = cursor.position()
        text_before_cursor = text[:cursor_pos]
        
        last_space_idx = max(text_before_cursor.rfind(' '), text_before_cursor.rfind('\n'))
        
        new_text = text[:last_space_idx + 1] + item.text() + " " + text[cursor_pos:]
        self.setPlainText(new_text)
        
        new_cursor = self.textCursor()
        new_cursor.setPosition(last_space_idx + 1 + len(item.text()) + 1)
        self.setTextCursor(new_cursor)
        
        self.completer_list.hide()
        self.setFocus()
        
    def focusOutEvent(self, event):
        self.completer_list.hide()
        super().focusOutEvent(event)
        
    def keyPressEvent(self, event):
        if self.completer_list.isVisible():
            if event.key() == Qt.Key.Key_Down:
                self.completer_list.setCurrentRow((self.completer_list.currentRow() + 1) % max(1, self.completer_list.count()))
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Up:
                self.completer_list.setCurrentRow((self.completer_list.currentRow() - 1) % max(1, self.completer_list.count()))
                event.accept()
                return
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                item = self.completer_list.currentItem()
                if item:
                    self.insert_completion(item)
                else:
                    item = self.completer_list.item(0)
                    if item:
                        self.insert_completion(item)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Escape:
                self.completer_list.hide()
                event.accept()
                return
                
        if (event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.returnPressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        if source.hasImage():
            image = source.imageData()
            if image:
                self.imagePasted.emit(image)
            return
        # Parfois les navigateurs/OS copient aussi des urls de fichiers d'images locales
        if source.hasUrls():
            urls = source.urls()
            if urls:
                url = urls[0]
                if url.isLocalFile():
                    path = url.toLocalFile()
                    # BUGFIX (V4.4.0) : le module 'imghdr' a été SUPPRIMÉ de la
                    # bibliothèque standard en Python 3.13 -> coller un fichier
                    # image plantait. QImageReader fait le même travail.
                    from PyQt6.QtGui import QImage, QImageReader
                    if QImageReader(path).canRead():
                        img = QImage(path)
                        if not img.isNull():
                            self.imagePasted.emit(img)
                            return
        super().insertFromMimeData(source)

class ImageDropTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pasted_images = []

    def insertFromMimeData(self, source):
        import tempfile
        import os
        import uuid
        
        # Helper function to save and register image
        def process_image(img, original_name="image"):
            temp_dir = os.path.join(tempfile.gettempdir(), "agents_multi_fonction_images")
            os.makedirs(temp_dir, exist_ok=True)
            file_name = f"pasted_image_{uuid.uuid4().hex[:8]}.png"
            file_path = os.path.join(temp_dir, file_name)
            if img.save(file_path, "PNG"):
                self.pasted_images.append(file_path)
                self.insertPlainText(f"[Image jointe : {original_name}]\n")

        if source.hasImage():
            image = source.imageData()
            if image:
                process_image(image, "presse-papiers")
            return
            
        if source.hasUrls():
            urls = source.urls()
            if urls:
                from PyQt6.QtGui import QImage, QImageReader
                for url in urls:
                    if url.isLocalFile():
                        path = url.toLocalFile()
                        if QImageReader(path).canRead():
                            img = QImage(path)
                            if not img.isNull():
                                process_image(img, os.path.basename(path))
                                return
                                
        super().insertFromMimeData(source)


class ConnectionDialog(QDialog):
    """Fenêtre de dialogue pour choisir le mode et la méthode de connexion au démarrage."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Choix du Mode & Connexion")
        self.setModal(True)
        self.resize(350, 320)
        
        layout = QVBoxLayout(self)

        # 1. Choix du Mode d'Application
        layout.addWidget(QLabel("1. Choisissez le mode de l'application :"))
        self.mode_group = QButtonGroup(self)
        self.radio_mode_general = QRadioButton("🤖 Assistant Général")
        self.radio_mode_coder = QRadioButton("💻 Agent Codeur")
        self.radio_mode_hardware = QRadioButton("🔌 Agent Concepteur (SKIDL)")
        self.radio_mode_meca = QRadioButton("⚙️ Agent Concepteur 3D (Mécanique)")
        self.mode_group.addButton(self.radio_mode_general)
        self.mode_group.addButton(self.radio_mode_coder)
        self.mode_group.addButton(self.radio_mode_hardware)
        self.mode_group.addButton(self.radio_mode_meca)
        self.radio_mode_general.setChecked(True)
        layout.addWidget(self.radio_mode_general)
        layout.addWidget(self.radio_mode_coder)
        layout.addWidget(self.radio_mode_hardware)
        layout.addWidget(self.radio_mode_meca)

        layout.addSpacing(15)

        # 2. Choix de la Méthode de Connexion
        layout.addWidget(QLabel("2. Choisissez votre méthode de connexion à l'IA :"))

        self.auth_group = QButtonGroup(self)
        self.radio_google_claude = QRadioButton("🔑 Google GenAI + Claude")
        self.radio_lmstudio = QRadioButton("🏠 LM Studio (SDK Natif Local)")
        self.auth_group.addButton(self.radio_google_claude)
        self.auth_group.addButton(self.radio_lmstudio)
        # Sélection par défaut
        self.radio_google_claude.setChecked(True)

        layout.addWidget(self.radio_google_claude)
        layout.addWidget(self.radio_lmstudio)
        
        layout.addSpacing(15)
        
        self.demo_checkbox = QCheckBox("🧪 Activer le Mode Démonstration (Dossier temporaire, Gemma 31B)")
        layout.addWidget(self.demo_checkbox)
        
        layout.addSpacing(10)
        
        self.settings_btn = QPushButton("⚙️ Réglages")
        self.settings_btn.setToolTip("Paramètres de l'application")
        self.settings_btn.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_btn)
        
        self.github_btn = QPushButton("🐙 GitHub")
        self.github_btn.setToolTip("Afficher les tutoriels GitHub (Création et Mise à jour)")
        self.github_btn.clicked.connect(self.show_github_tutorials)
        layout.addWidget(self.github_btn)
        
        layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Démarrer")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def open_settings(self):
        from PyQt6.QtCore import QSettings
        settings = QSettings("Antigravity", "LAtelierIA")
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Réglages")
        dialog.resize(400, 150)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("<b>Paramètres de l'application</b>"))
        
        cb_auto_clean = QCheckBox("Nettoyer le dossier docs_gen/ (Assistant Général) lors du nettoyage")
        # Par défaut True (vrai)
        cb_auto_clean.setChecked(settings.value("auto_clean_docs_gen", True, type=bool))
        layout.addWidget(cb_auto_clean)
        
        cb_auto_clean_ds = QCheckBox("Nettoyer le dossier data_sheets/ (Mode Hardware) lors du nettoyage")
        cb_auto_clean_ds.setChecked(settings.value("auto_clean_data_sheets", True, type=bool))
        layout.addWidget(cb_auto_clean_ds)
        
        cb_graphify_code_only = QCheckBox("Graphify : Indexer uniquement le code (Économique / Rapide)")
        cb_graphify_code_only.setChecked(settings.value("graphify_code_only", True, type=bool))
        layout.addWidget(cb_graphify_code_only)
        
        layout.addWidget(QLabel("<b>Clé API dédiée pour Graphify :</b>"))
        combo_graphify_key = QComboBox()
        combo_graphify_key.addItems([
            "Même clé que l'agent (Défaut)",
            "Forcer la Clé 2 (Optionnelle)"
        ])
        combo_graphify_key.setCurrentIndex(settings.value("graphify_api_key_choice", 0, type=int))
        layout.addWidget(combo_graphify_key)
        
        layout.addWidget(QLabel("<b>Modèle LLM pour Graphify (optionnel) :</b>"))
        combo_graphify_model = QComboBox()
        combo_graphify_model.setEditable(True)
        
        def update_graphify_models(index):
            combo_graphify_model.clear()
            if index == 0:
                combo_graphify_model.addItems(["Par défaut (Auto)", "gemma-4-31b-it"])
            elif index == 1:
                combo_graphify_model.addItems(["Par défaut (Auto)", "gemini-3.1-pro-preview", "gemini-3.1-pro-preview-extended", "gemini-3.6-flash", "gemini-3.6-flash-thinking"])
            
            # Essayer de restaurer la valeur sauvegardée, sinon 0
            saved = settings.value("graphify_model_name", "Par défaut (Auto)", type=str)
            if combo_graphify_model.findText(saved) != -1:
                combo_graphify_model.setCurrentText(saved)
            else:
                combo_graphify_model.setCurrentIndex(0)

        combo_graphify_key.currentIndexChanged.connect(update_graphify_models)
        
        # Initialisation avec l'index actuel
        update_graphify_models(combo_graphify_key.currentIndex())
        layout.addWidget(combo_graphify_model)
        
        test_btn = QPushButton("Tester la connexion (LLM)")
        def test_graphify_connection():
            idx = combo_graphify_key.currentIndex()
            if idx == 0:
                filepath = settings.value("api_file_path", "", type=str)
            elif idx == 1:
                filepath = settings.value("api_file_path_2", "", type=str)
            
            api_key = ""
            import os
            if filepath and os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        api_key = f.read().strip()
                except Exception:
                    pass
            
            if not api_key:
                QMessageBox.warning(dialog, "Erreur", "Aucune clé API trouvée pour ce mode (fichier introuvable ou vide).")
                return
                
            model = combo_graphify_model.currentText()
            if model == "Par défaut (Auto)":
                if idx == 0: model = "gemma-4-31b-it"
                elif idx == 1: model = "gemini-3.1-pro-preview"
                
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                res_text = ""
                from google import genai
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model,
                    contents="Réponds juste 'Test OK'."
                )
                res_text = response.text
                
                QApplication.restoreOverrideCursor()
                QMessageBox.information(dialog, "Succès", f"Connexion LLM réussie avec {model} !\nRéponse : {res_text}")
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(dialog, "Erreur de connexion", f"Le modèle {model} a échoué :\n{e}")

        test_btn.clicked.connect(test_graphify_connection)
        layout.addWidget(test_btn)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("Enregistrer")
        def save_and_close():
            settings.setValue("auto_clean_docs_gen", cb_auto_clean.isChecked())
            settings.setValue("auto_clean_data_sheets", cb_auto_clean_ds.isChecked())
            settings.setValue("graphify_code_only", cb_graphify_code_only.isChecked())
            settings.setValue("graphify_api_key_choice", combo_graphify_key.currentIndex())
            settings.setValue("graphify_model_name", combo_graphify_model.currentText())
            dialog.accept()
            
        save_btn.clicked.connect(save_and_close)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()

    def show_github_tutorials(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Tutoriels GitHub - L'Atelier IA")
        dialog.resize(600, 550)
        
        layout = QVBoxLayout(dialog)
        
        msg = """<h3>🛑 Manuel de création d'un dépôt Git :</h3>
<p><b>1. Création du dépôt distant (GitHub)</b></p>
<ul>
  <li>Connectez-vous à votre compte GitHub.</li>
  <li>Cliquez sur "New" en haut à gauche.</li>
  <li>Donnez un nom à votre dépôt.</li>
  <li>Laissez les cases "Initialize this repository with..." décochées.</li>
  <li>Cliquez sur "Create repository" et copiez l'URL du dépôt.</li>
</ul>

<p><b>2. Initialisation locale et envoi</b><br>
Ouvrez votre terminal directement dans le dossier du projet et exécutez :</p>

<pre style="background-color: #2d2d30; padding: 10px; font-family: Consolas, monospace; color: #ce9178; font-size: 14px; border-left: 3px solid #0e639c;"># 1. Initialiser le dossier comme un dépôt Git
git init

# 2. Ajouter tous les fichiers du dossier
git add .

# 3. Créer le premier point de sauvegarde (commit)
git commit -m "Premier commit : initialisation du projet"

# 4. Renommer la branche principale en 'main'
git branch -M main

# 5. Connecter le dossier local au dépôt distant (remplacez l'URL)
git remote add origin https://github.com/votre-nom/nom-du-repo.git

# 6. Envoyer vos fichiers vers GitHub
git push -u origin main</pre>

<hr>

<h3>🚀 Commandes de mise à jour (Trio magique) :</h3>
<p>1. Vérifier l'état de vos fichiers :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git status</code></p>

<p>2. Préparer les modifications (Staging) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git add .</code></p>

<p>3. Enregistrer les modifications localement (Commit) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git commit -m "Description de la modification apportée"</code></p>

<p>4. Envoyer les modifications sur GitHub (Push) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git push</code></p>"""
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(msg)
        layout.addWidget(text_edit)
        
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("📋 Copier tout le texte")
        copy_btn.setObjectName("Accent")
        
        def copy_to_clipboard():
            QApplication.clipboard().setText(text_edit.toPlainText())
            copy_btn.setText("✅ Copié !")
            QTimer.singleShot(2000, lambda: copy_btn.setText("📋 Copier tout le texte"))
            
        copy_btn.clicked.connect(copy_to_clipboard)
        
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(dialog.accept)
        
        btn_layout.addWidget(copy_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()

    def get_selection(self):
        app_mode = "general"
        if self.radio_mode_coder.isChecked():
            app_mode = "coder"
        elif self.radio_mode_hardware.isChecked():
            app_mode = "hardware"
        elif self.radio_mode_meca.isChecked():
            app_mode = "meca"

        auth_mode = "google_claude"
        if self.radio_lmstudio.isChecked():
            auth_mode = "lm_studio"
            
        is_demo = self.demo_checkbox.isChecked()
            
        return auth_mode, app_mode, is_demo


class CheckableFileSystemModel(QFileSystemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.checked_paths = set()
        self.unchecked_paths = set()

    def flags(self, index):
        default_flags = super().flags(index)
        if not index.isValid():
            return default_flags
        if index.column() == 0:
            return default_flags | Qt.ItemFlag.ItemIsUserCheckable
        return default_flags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            path = self.filePath(index)
            if self.is_path_checked(path):
                return Qt.CheckState.Checked.value
            return Qt.CheckState.Unchecked.value
        return super().data(index, role)

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            path = self.filePath(index)
            if value == Qt.CheckState.Checked.value:
                self.checked_paths.add(path)
                self.unchecked_paths.discard(path)
            else:
                self.unchecked_paths.add(path)
                self.checked_paths.discard(path)
            self.dataChanged.emit(index, index, [role])
            self.layoutChanged.emit()
            return True
        return super().setData(index, value, role)

    def is_path_checked(self, path):
        try:
            p = Path(path).resolve(strict=False)
            best_match_len = -1
            is_checked = False
            
            for c_path in self.checked_paths:
                c_p = Path(c_path).resolve(strict=False)
                if p == c_p or p.is_relative_to(c_p):
                    match_len = len(c_p.parts)
                    if match_len > best_match_len:
                        best_match_len = match_len
                        is_checked = True
                        
            for u_path in self.unchecked_paths:
                u_p = Path(u_path).resolve(strict=False)
                if p == u_p or p.is_relative_to(u_p):
                    match_len = len(u_p.parts)
                    if match_len > best_match_len:
                        best_match_len = match_len
                        is_checked = False
                        
            return is_checked
        except Exception:
            pass
        return False

    def check_all(self):
        root = self.rootPath()
        if root:
            self.checked_paths.clear()
            self.unchecked_paths.clear()
            self.checked_paths.add(root)
            self.layoutChanged.emit()

    def uncheck_all(self):
        self.checked_paths.clear()
        self.unchecked_paths.clear()
        self.layoutChanged.emit()

from core.nodal_graph import NodeItem, EdgeItem, NodeGraphWidget
from PyQt6.QtGui import QColor, QBrush, QPen, QPainter, QFont
from PyQt6.QtCore import Qt, QRectF, QPointF

class GraphifyThemeNodeItem(NodeItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow_color = QColor(46, 204, 113, int(40 + 60 * self._glow_intensity))
        border_color = QColor(46, 204, 113)
        circle_radius = 18
        circle_center = QPointF(0, -self.height/2 + 30)
        
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(circle_center, circle_radius + 12, circle_radius + 12)
            
        base_color = QColor(10, 17, 14) 
        painter.setBrush(QBrush(base_color))
        pen = QPen(border_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawEllipse(circle_center, circle_radius, circle_radius)
        
        painter.setPen(QPen(QColor(230, 240, 235)))
        font_header = QFont("Consolas", 10, QFont.Weight.Bold)
        painter.setFont(font_header)
        rect_text = QRectF(-self.width/2, -self.height/2 + 55, self.width, 25)
        painter.drawText(rect_text, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop, self.label)

class GraphifyThemeEdgeItem(EdgeItem):
    def paint(self, painter, option, widget):
        if not self.source_node or not self.dest_node: return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        edge_path = self._get_path()
        is_hovered = self.isUnderMouse()
        
        color = QColor(46, 204, 113, 180) if is_hovered else QColor(40, 90, 60, 120)
        pen = QPen(color)
        pen.setWidth(3 if is_hovered else 2)
        painter.setPen(pen)
        painter.drawPath(edge_path)
        
        if hasattr(self, 'label') and self.label:
            painter.setPen(QPen(QColor(46, 204, 113)))
            font = QFont("Consolas", 8, QFont.Weight.Normal, italic=True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(self.label)
            th = fm.height()
            p1 = self.source_node.pos()
            p2 = self.dest_node.pos()
            center = (p1 + p2) / 2.0
            painter.drawText(QRectF(center.x() - tw/2, center.y() - th/2, tw, th), Qt.AlignmentFlag.AlignCenter, self.label)

class GraphifyThemeNodeGraphWidget(NodeGraphWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #050a08; border: none;")
        self.reset_graph(keep_defaults=False)
        
    def add_node(self, node_id, label=""):
        if not label: label = node_id
        if node_id not in self.nodes:
            node = GraphifyThemeNodeItem(node_id, label, self)
            self.nodes[node_id] = node
            self.scene.addItem(node)
        return self.nodes[node_id]

    def add_edge(self, source_id, dest_id):
        if source_id in self.nodes and dest_id in self.nodes:
            edge = GraphifyThemeEdgeItem(self.nodes[source_id], self.nodes[dest_id])
            self.edges.append(edge)
            self.scene.addItem(edge)
            return edge
        return None

class GraphifyManualDialog(QDialog):
    def __init__(self, sandbox, api_key_graphify, graphify_model_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Graphify Manuel")
        self.setMinimumSize(800, 700)
        self.sandbox = sandbox
        self.api_key_graphify = api_key_graphify
        self.graphify_model_name = graphify_model_name
        self._worker = None

        layout = QVBoxLayout(self)

        # Sélection commande
        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(QLabel("<b>Commande :</b>"))
        self.cmd_combo = QComboBox()
        self.cmd_combo.addItems(["path (Chemin)", "explain (Expliquer)", "query (Recherche libre)"])
        self.cmd_combo.currentIndexChanged.connect(self._on_cmd_changed)
        cmd_layout.addWidget(self.cmd_combo)
        layout.addLayout(cmd_layout)

        # Paramètres dynamiques
        self.param_layout = QVBoxLayout()
        self.input_a = QLineEdit()
        self.input_b = QLineEdit()
        self.label_a = QLabel("Nœud A :")
        self.label_b = QLabel("Nœud B :")
        
        self.param_layout.addWidget(self.label_a)
        self.param_layout.addWidget(self.input_a)
        self.param_layout.addWidget(self.label_b)
        self.param_layout.addWidget(self.input_b)
        layout.addLayout(self.param_layout)

        # Exécuter
        self.exec_btn = QPushButton("🚀 Exécuter")
        self.exec_btn.clicked.connect(self.execute_command)
        layout.addWidget(self.exec_btn)

        # Résultat
        layout.addWidget(QLabel("<b>Résultat :</b>"))
        
        from PyQt6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")
        self.result_text.setMaximumHeight(150)
        splitter.addWidget(self.result_text)
        
        self.local_graph = GraphifyThemeNodeGraphWidget()
        splitter.addWidget(self.local_graph)
        
        layout.addWidget(splitter)
        
        self._on_cmd_changed(0)

    def _on_cmd_changed(self, idx):
        self.input_a.clear()
        self.input_b.clear()
        if idx == 0: # path
            self.label_a.setText("Nœud A (ex: FastAPI) :")
            self.label_a.show()
            self.input_a.show()
            self.label_b.setText("Nœud B (ex: ModelField) :")
            self.label_b.show()
            self.input_b.show()
        elif idx == 1: # explain
            self.label_a.setText("Nœud à expliquer (ex: parse_data) :")
            self.label_a.show()
            self.input_a.show()
            self.label_b.hide()
            self.input_b.hide()
        elif idx == 2: # query
            self.label_a.setText("Question (ex: Quels sont les endpoints liés à la base de données ?) :")
            self.label_a.show()
            self.input_a.show()
            self.label_b.hide()
            self.input_b.hide()

    def execute_command(self):
        if not self.sandbox:
            QMessageBox.warning(self, "Erreur", "Ouvrez d'abord un dossier projet.")
            return

        cmd = self.cmd_combo.currentIndex()
        val_a = self.input_a.text().strip()
        val_b = self.input_b.text().strip()

        if cmd == 0:
            if not val_a or not val_b:
                QMessageBox.warning(self, "Erreur", "Veuillez remplir les deux nœuds.")
                return
            self._run_worker(self.sandbox.graphify_path, val_a, val_b, self.api_key_graphify, self.graphify_model_name)
        elif cmd == 1:
            if not val_a:
                QMessageBox.warning(self, "Erreur", "Veuillez entrer un nœud.")
                return
            self._run_worker(self.sandbox.graphify_explain, val_a, self.api_key_graphify, self.graphify_model_name)
        elif cmd == 2:
            if not val_a:
                QMessageBox.warning(self, "Erreur", "Veuillez entrer une question.")
                return
            self._run_worker(self.sandbox.graphify_query, val_a, self.api_key_graphify, self.graphify_model_name)

    def _run_worker(self, func, *args):
        self.exec_btn.setEnabled(False)
        self.exec_btn.setText("⏳ Exécution en cours...")
        self.result_text.clear()
        
        self._worker = FunctionWorker(func, *args)
        self._worker.finished_task.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, success, result):
        self.exec_btn.setEnabled(True)
        self.exec_btn.setText("🚀 Exécuter")
        if success:
            self.result_text.setPlainText(str(result))
            self.local_graph.display_graphify_output(str(result))
        else:
            self.result_text.setPlainText(f"❌ Erreur : {result}")

class MainWindow(QMainWindow):
    def __init__(self, auth_mode, app_mode="coder", is_demo=False):
        super().__init__()
        self.auth_mode = auth_mode
        self.app_mode = app_mode
        self.is_demo = is_demo
        # V4.3.0 : titre synchronisé avec la version de main.py (le titre
        # affichait encore « V3.8 »).
        self.setWindowTitle("L'Atelier IA — V4.4.0")
        self.resize(1400, 860)

        self.settings = QSettings("Antigravity", "LAtelierIA")
        # SÉCURITÉ (V4.4.0) : le fichier de clé était partagé entre les modes
        # « Clé API (Google) » et « Claude » (même clé QSettings). Un
        # utilisateur alternant les modes envoyait sa clé Google à l'API
        # Anthropic (et inversement) avant même le 401 — fuite de clé vers le
        # mauvais fournisseur. Chaque mode a désormais son propre réglage
        # (l'ancien 'api_file_path' est conservé comme valeur du mode Google
        # pour ne pas perdre la configuration existante).
        self._api_key_setting = ("api_file_path_claude" if auth_mode == "claude"
                                 else "api_file_path")
        self.api_file_path = self.settings.value(self._api_key_setting, "")
        self.api_file_path_2 = self.settings.value("api_file_path_2", "")
        self.api_file_path_claude = self.settings.value("api_file_path_claude", "")
        self.save_directory = self.settings.value("last_dir", "")
        self.project_root = self.save_directory
        self.lm_url_saved = self.settings.value("lm_url", "127.0.0.1:1234")
        self.wants_to_go_back = False
        
        self.test_worker = None
        self.live_worker = None
        self.gen_worker = None
        
        self.selected_images_live = []
        self.selected_images_gen = []
        
        self.last_live_mission = ""
        self.last_live_images = []
        
        self.current_file = None
        self.sandbox = None
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.fileChanged.connect(self.on_file_changed_externally)
        
        self.project_agents = {}
        self.json_agents = {}

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self._build_file_panel(), "Fichiers")
        self.editor_panel = self._build_editor_panel()
        if self.app_mode != "hardware":
            self.left_tabs.addTab(self.editor_panel, "Editeur")
            
        if self.app_mode != "general":
            splitter.addWidget(self.left_tabs)
        else:
            self.left_tabs.hide()
        
        self.node_graph = NodeGraphWidget()
        self.node_graph.node_clicked.connect(self.show_agent_details)
        self.node_graph.edge_hovered.connect(self.show_edge_details)
        self.node_graph.edge_hover_left.connect(self.hide_edge_details)
            
        splitter.addWidget(self.node_graph)
        
        self.right_panel_container = QWidget()
        self.right_panel_layout = QVBoxLayout(self.right_panel_container)
        self.right_panel_layout.setContentsMargins(0, 0, 0, 0)
        
        if self.app_mode == "coder":
            from ui_coder import CoderPanel
            self.right_panel = CoderPanel(self)
        elif self.app_mode == "hardware":
            from ui_hardware import HardwarePanel
            self.right_panel = HardwarePanel(self)
        elif self.app_mode == "meca":
            from ui_meca import MecaPanel
            self.right_panel = MecaPanel(self)
        else:
            from ui_general import GeneralPanel
            self.right_panel = GeneralPanel(self)
            
        self.right_panel_layout.addWidget(self.right_panel)
        splitter.addWidget(self.right_panel_container)
        
        if self.app_mode != "general":
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 7)
            splitter.setStretchFactor(2, 3)
            splitter.setSizes([10, 970, 420])
        else:
            splitter.setStretchFactor(0, 7)
            splitter.setStretchFactor(1, 3)
            splitter.setSizes([970, 420])
            
        root_layout.addWidget(splitter, 1)
        
        if self.is_demo:
            QTimer.singleShot(500, self.setup_demo)

    def setup_demo(self):
        import tempfile
        import os
        from PyQt6.QtWidgets import QMessageBox
        
        # Create a directory at the project level
        temp_dir = os.path.join(os.getcwd(), "agent_demo_" + self.app_mode)
        os.makedirs(temp_dir, exist_ok=True)
        self.demo_dir_path = temp_dir
        
        # Open it automatically
        self.open_folder(path=temp_dir)
        
        self.add_system_message(f"🧪 <b>Mode Démonstration Actif</b><br>Dossier temporaire créé et ouvert : {self._esc(temp_dir)}<br><i>Vous pouvez maintenant lancer la démonstration via le bouton '🧪 Démo technique'.</i>")

    def run_graphify(self):
        if not self.sandbox:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return

        import shutil
        if not hasattr(self, "_graphify_tool_path"):
            self._graphify_tool_path = None
        
        # Si l'outil n'est pas dans le PATH global (ce qui n'est pas votre cas), on demande son emplacement
        if not shutil.which("graphify") and not self._graphify_tool_path:
            dir_path = QFileDialog.getExistingDirectory(
                self, 
                "Où se trouve l'outil Graphify (dossier contenant graphify.exe) ?"
            )
            if dir_path:
                self._graphify_tool_path = dir_path
                import os
                # On ajoute ce dossier temporairement au PATH de l'application
                os.environ["PATH"] = dir_path + os.pathsep + os.environ.get("PATH", "")
            else:
                QMessageBox.warning(self, "Erreur", "Le dossier contenant l'outil Graphify est requis.")
                return


        selected_path = "."
        indexes = self.tree_view.selectionModel().selectedIndexes()
        if indexes:
            idx = [i for i in indexes if i.column() == 0]
            if idx:
                path = self.fs_model.filePath(idx[0])
                selected_path = path
                
                try:
                    rel_path = os.path.relpath(selected_path, self.sandbox.root)
                    if not rel_path.startswith(".."):
                        selected_path = rel_path
                    else:
                        selected_path = "."
                except ValueError:
                    selected_path = "."

        if selected_path not in (".", ""):
            reply = QMessageBox.question(
                self, "Graphify", 
                f"Voulez-vous analyser uniquement le dossier sélectionné ('{selected_path}') ?\n\n"
                "Oui : Analyser uniquement ce dossier\n"
                "Non : Analyser tout le projet",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                selected_path = "."

        # v4.2.0 : plus AUCUNE clé API transmise au binaire tiers 'graphify'.
        # Le build est purement structurel (--code-only) ; l'enrichissement
        # sémantique (GRAPH_REPORT.md) est fait par « 🧠 Analyse Graphify ».
        # ROBUSTESSE (V4.4.0) : le build (subprocess, timeout 300 s) tournait
        # sur le thread PRINCIPAL -> interface figée jusqu'à 5 minutes. Il est
        # désormais exécuté dans un FunctionWorker.
        self.graphify_btn.setEnabled(False)
        self.graphify_btn.setText("⏳ Construction...")
        
        from PyQt6.QtCore import QSettings
        settings = QSettings("Antigravity", "LAtelierIA")
        code_only = settings.value("graphify_code_only", True, type=bool)

        self._graphify_build_worker = FunctionWorker(self.sandbox.graphify_build, target_dir=selected_path, code_only=code_only)
        self._graphify_build_worker.finished_task.connect(self._on_graphify_build_finished)
        self._graphify_build_worker.start()

    def _on_graphify_build_finished(self, success, result):
        self.graphify_btn.setEnabled(True)
        self.graphify_btn.setText("🚀 Graphify")
        if not success:
            result = f"Erreur inattendue : {result}"

        if "succès" in str(result).lower():
            self.add_system_message("🚀 <b>Graphe Graphify (structure) généré !</b><br>"
                                    "Aucune clé API n'a été transmise au binaire. "
                                    "Cliquez sur « 🧠 Analyse Graphify » pour générer "
                                    "GRAPH_REPORT.md avec votre LLM.")
            QMessageBox.information(self, "Graphify",
                                    "Le graphe structurel a été construit avec succès !\n\n"
                                    "Étape suivante : « 🧠 Analyse Graphify » pour générer "
                                    "le rapport (GRAPH_REPORT.md) via votre LLM.")

        else:
            self.add_system_message(f"❌ <b>Erreur Graphify</b> : {self._esc(str(result))}")
            QMessageBox.critical(self, "Erreur Graphify", str(result))

    def run_index_rag(self):
        if not self.sandbox:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return
            
        self.index_rag_btn.setEnabled(False)
        self.index_rag_btn.setText("⏳ Indexation...")
        
        # We can use a FunctionWorker to avoid freezing UI
        worker = FunctionWorker(self.sandbox.build_vector_index)
        worker.finished_task.connect(self._on_index_rag_finished)
        worker.start()
        # Keep a reference to prevent garbage collection
        self._index_rag_worker = worker

    def _on_index_rag_finished(self, success, result):
        self.index_rag_btn.setEnabled(True)
        self.index_rag_btn.setText("🧠 Index RAG")
        if success and "SUCCÈS" in str(result):
            self.add_system_message(f"🧠 <b>Index RAG généré !</b><br>{self._esc(str(result))}")
            QMessageBox.information(self, "Index RAG", str(result))
        else:
            self.add_system_message(f"❌ <b>Erreur Indexation RAG</b> : {self._esc(str(result))}")
            QMessageBox.critical(self, "Erreur", str(result))

    def run_github_helper(self):
        if not self.sandbox:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return

        git_path = os.path.join(self.project_root, ".git")
        is_update = os.path.exists(git_path) and os.path.isdir(git_path)
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Mode GitHub - L'Atelier IA")
        dialog.resize(600, 450)
        
        layout = QVBoxLayout(dialog)
        
        if is_update:
            header = QLabel("🚀 <b>Dépôt Git détecté ! Voici les commandes de mise à jour :</b>")
            msg = """<p>1. Vérifier l'état de vos fichiers :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git status</code></p>

<p>2. Préparer les modifications (Staging) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git add .</code></p>

<p>3. Enregistrer les modifications localement (Commit) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git commit -m "Description de la modification apportée"</code></p>

<p>4. Envoyer les modifications sur GitHub (Push) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git push</code></p>

<hr>
<p><i>En résumé, le "trio" magique au quotidien :</i></p>

<pre style="background-color: #2d2d30; padding: 10px; font-family: Consolas, monospace; color: #ce9178; font-size: 14px; border-left: 3px solid #0e639c;">git add .
git commit -m "Mise à jour"
git push</pre>"""
        else:
            header = QLabel("🛑 <b>Aucun dépôt Git détecté. Voici le manuel de création :</b>")
            msg = """<p><b>1. Création du dépôt distant (GitHub)</b></p>
<ul>
  <li>Connectez-vous à votre compte GitHub.</li>
  <li>Cliquez sur "New" en haut à gauche.</li>
  <li>Donnez un nom à votre dépôt.</li>
  <li>Laissez les cases "Initialize this repository with..." décochées.</li>
  <li>Cliquez sur "Create repository" et copiez l'URL du dépôt.</li>
</ul>

<p><b>2. Initialisation locale et envoi</b><br>
Ouvrez votre terminal directement dans le dossier du projet et exécutez :</p>

<pre style="background-color: #2d2d30; padding: 10px; font-family: Consolas, monospace; color: #ce9178; font-size: 14px; border-left: 3px solid #0e639c;"># 1. Initialiser le dossier comme un dépôt Git
git init

# 2. Ajouter tous les fichiers du dossier
git add .

# 3. Créer le premier point de sauvegarde (commit)
git commit -m "Premier commit : initialisation du projet"

# 4. Renommer la branche principale en 'main'
git branch -M main

# 5. Connecter le dossier local au dépôt distant (remplacez l'URL)
git remote add origin https://github.com/votre-nom/nom-du-repo.git

# 6. Envoyer vos fichiers vers GitHub
git push -u origin main</pre>"""
        
        layout.addWidget(header)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(msg)
        layout.addWidget(text_edit)
        
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("📋 Copier tout le texte")
        copy_btn.setObjectName("Accent")
        
        def copy_to_clipboard():
            QApplication.clipboard().setText(text_edit.toPlainText())
            copy_btn.setText("✅ Copié !")
            QTimer.singleShot(2000, lambda: copy_btn.setText("📋 Copier tout le texte"))
            
        copy_btn.clicked.connect(copy_to_clipboard)
        
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(dialog.accept)
        
        btn_layout.addWidget(copy_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()

    def open_manual_graphify(self):
        if not self.sandbox:
            QMessageBox.warning(self, "Erreur", "Ouvrez d'abord un dossier projet.")
            return
            
        choice = self.settings.value("graphify_api_key_choice", 0, type=int)
        if choice == 0:
            g_key = self.api_file_path
        elif choice == 1:
            g_key = self.api_file_path_2
        else:
            g_key = self.api_file_path_claude
            
        model = self.settings.value("graphify_model_name", "Par défaut (Auto)", type=str)
        if model == "Par défaut (Auto)":
            model = None
            
        dialog = GraphifyManualDialog(self.sandbox, g_key, model, self)
        dialog.exec()

    def closeEvent(self, event):
        """Gestion propre de la fermeture pour annuler les threads en cours."""
        # BUGFIX (V4.3.0) : le worker d'Analyse Graphify manquait à la liste
        # -> « QThread: Destroyed while thread is still running » possible si
        # l'application était fermée pendant une analyse.
        # V4.4.0 : ajout des FunctionWorker (build Graphify, tâches Hardware) ;
        # et l'événement n'était accepté qu'après 2 s d'attente MÊME si le
        # thread vivait encore (abort garanti à la destruction). On attend
        # désormais plus longtemps, puis terminate() en tout dernier recours
        # (préférable à l'abort du process entier).
        workers = [self.live_worker, self.gen_worker, self.test_worker,
                   getattr(self, 'graphify_analysis_worker', None),
                   getattr(self, '_graphify_build_worker', None),
                   getattr(self, '_task_worker', None)]
        for w in workers:
            if w and w.isRunning():
                if hasattr(w, "cancel"):
                    w.cancel()
                if not w.wait(5000):
                    logger.warning("[FERMETURE] Un worker ne répond pas après 5 s : "
                                   "arrêt forcé (terminate).")
                    w.terminate()
                    w.wait(1000)
                    
        # Suppression du dossier de démo si on était en mode démo
        if getattr(self, 'is_demo', False) and getattr(self, 'demo_dir_path', None):
            import shutil
            import os
            try:
                if os.path.exists(self.demo_dir_path):
                    shutil.rmtree(self.demo_dir_path)
            except Exception as e:
                logger.warning(f"[FERMETURE] Impossible de supprimer le dossier de démo {self.demo_dir_path}: {e}")
                
        event.accept()

    # ============================ TOOLBAR ============================
    def _build_toolbar(self):
        bar = QFrame(); bar.setObjectName("Toolbar")
        bar.setFixedHeight(46)
        h = QHBoxLayout(bar); h.setContentsMargins(8, 6, 8, 6); h.setSpacing(6)

        self.back_btn = QPushButton("← Retour")
        self.back_btn.clicked.connect(self.go_back)
        h.addWidget(self.back_btn)

        self.open_btn = QPushButton("📂 Ouvrir un dossier")
        self.open_btn.setObjectName("Accent")
        self.open_btn.clicked.connect(self.open_folder)
        h.addWidget(self.open_btn)

        h.addWidget(self._vsep())

        if self.auth_mode in ("api_key", "claude", "google_claude"):
            label = "🔑 Clé 1" if self.auth_mode in ("api_key", "google_claude") else "🔑 Clé Claude"
            self.api_btn = QPushButton(label)
            tt = "Clé API principale.\nUtilisée par défaut." if self.auth_mode in ("api_key", "google_claude") else "Fichier de clé API OneProvider."
            self.api_btn.setToolTip(tt)
            self.api_btn.clicked.connect(self.browse_api_file)
            saved_key_label = os.path.basename(self.api_file_path) if (self.api_file_path and os.path.exists(self.api_file_path)) else "aucun fichier"
            self.api_file_input = QLabel(saved_key_label); self.api_file_input.setObjectName("Muted")
            h.addWidget(self.api_btn); h.addWidget(self.api_file_input)

            if self.auth_mode in ("api_key", "google_claude"):
                self.api_btn2 = QPushButton("🔑 Clé 2")
                self.api_btn2.setToolTip("Clé API secondaire OPTIONNELLE (ex : forfait payant).\n"
                                         "Utilisée uniquement pour les modèles listés dans\n"
                                         "MODELS_ON_KEY_2 (utils.py), ex : Gemini 3.1 Pro.\n"
                                         "Si aucune Clé 2 n'est fournie, la Clé 1 sert pour tout.")
                self.api_btn2.clicked.connect(self.browse_api_file_2)
                saved_key2_label = os.path.basename(self.api_file_path_2) if (self.api_file_path_2 and os.path.exists(self.api_file_path_2)) else "(optionnelle)"
                self.api_file_input2 = QLabel(saved_key2_label); self.api_file_input2.setObjectName("Muted")
                self.api_clear2_btn = QPushButton("✖")
                self.api_clear2_btn.setFixedWidth(24)
                self.api_clear2_btn.setToolTip("Retirer la Clé 2 (tout repassera sur la Clé 1).")
                self.api_clear2_btn.clicked.connect(self.clear_api_file_2)
                h.addWidget(self.api_btn2); h.addWidget(self.api_file_input2); h.addWidget(self.api_clear2_btn)

            if self.auth_mode == "google_claude":
                self.api_btn_claude = QPushButton("🔑 Clé Claude")
                self.api_btn_claude.setToolTip("Clé API Anthropic OPTIONNELLE.\nPermet d'utiliser les modèles Claude.")
                self.api_btn_claude.clicked.connect(self.browse_api_file_claude)
                saved_key_claude_label = os.path.basename(self.api_file_path_claude) if (self.api_file_path_claude and os.path.exists(self.api_file_path_claude)) else "(optionnelle)"
                self.api_file_input_claude = QLabel(saved_key_claude_label); self.api_file_input_claude.setObjectName("Muted")
                self.api_clear_claude_btn = QPushButton("✖")
                self.api_clear_claude_btn.setFixedWidth(24)
                self.api_clear_claude_btn.setToolTip("Retirer la Clé Claude.")
                self.api_clear_claude_btn.clicked.connect(self.clear_api_file_claude)
                h.addWidget(self.api_btn_claude); h.addWidget(self.api_file_input_claude); h.addWidget(self.api_clear_claude_btn)

        elif self.auth_mode == "lm_studio":
            h.addWidget(QLabel("🖥️ LM Studio"))
            self.lm_url_input = QLineEdit(self.lm_url_saved)
            self.lm_url_input.setFixedWidth(170)
            self.lm_url_input.textChanged.connect(lambda t: self.settings.setValue("lm_url", t))
            h.addWidget(self.lm_url_input)

        self.test_btn = QPushButton("🧪 Tester")
        self.test_btn.clicked.connect(self.test_connection)
        h.addWidget(self.test_btn)

        self.rapport_btn = QPushButton("📋 Rapport")
        self.rapport_btn.clicked.connect(self.generate_report)
        h.addWidget(self.rapport_btn)

        h.addWidget(self._vsep())
        h.addStretch()
        return bar

    def _vsep(self):
        line = QFrame(); line.setFrameShape(QFrame.Shape.VLine); line.setObjectName("Sep")
        line.setFixedHeight(26)
        return line

    def generate_report(self):
        report_lines = []
        report_lines.append("=== COMPTE RENDU DES DISCUSSIONS ===")
        
        # Récupération de l'historique Général (si applicable)
        if hasattr(self, 'gen_history') and self.gen_history:
            report_lines.append("\n--- Mode Assistant Général ---")
            for msg in self.gen_history:
                role = "🤖 Assistant" if msg.get('role') == "assistant" else "👤 Utilisateur"
                report_lines.append(f"\n[{role}]")
                report_lines.append(str(msg.get('content', '')))
                
        # Récupération des historiques LiveAgent (Codeur/Hardware)
        histories = {}
        if self.live_worker and hasattr(self.live_worker, 'full_agent_histories') and self.live_worker.full_agent_histories:
            histories = self.live_worker.full_agent_histories
        elif self.live_worker and hasattr(self.live_worker, 'agent_histories') and self.live_worker.agent_histories:
            histories = self.live_worker.agent_histories
        elif hasattr(self, 'project_root') and self.project_root and os.path.exists(os.path.join(self.project_root, ".agent_recovery.json")):
            try:
                import json
                with open(os.path.join(self.project_root, ".agent_recovery.json"), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    histories = data.get("full_agent_histories") or data.get("agent_histories", {})
            except Exception:
                pass
                
        if histories:
            report_lines.append("\n--- Mode Multi-Agents ---")
            for agent_id, history in histories.items():
                report_lines.append(f"\n======================================")
                report_lines.append(f"AGENT : {agent_id}")
                report_lines.append(f"======================================")
                for msg in history:
                    role = "🤖 Agent" if msg.get('role') == "assistant" else "👤 Système/User"
                    ts = msg.get('timestamp', '')
                    if ts:
                        report_lines.append(f"\n[{role} - {ts}]")
                    else:
                        report_lines.append(f"\n[{role}]")
                        
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        content_str = ""
                        for part in content:
                            if part.get("type") == "text":
                                content_str += part.get("text", "")
                            elif part.get("type") == "image":
                                content_str += "[Image fournie]\n"
                        report_lines.append(content_str)
                    else:
                        report_lines.append(str(content))
        
        if len(report_lines) == 1:
            QMessageBox.information(self, "Rapport", "Aucune discussion trouvée.")
            return

        report_text = "\n".join(report_lines)
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Rapport des discussions")
        dialog.resize(900, 700)
        layout = QVBoxLayout(dialog)
        
        plain_edit = QPlainTextEdit()
        plain_edit.setReadOnly(True)
        plain_edit.setPlainText(report_text)
        mono_font = QFont("Consolas")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setPointSize(10)
        plain_edit.setFont(mono_font)
        
        layout.addWidget(plain_edit)
        
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("📋 Copier tout")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(report_text))
        
        save_btn = QPushButton("💾 Sauvegarder (TXT)")
        def save_file():
            path, _ = QFileDialog.getSaveFileName(dialog, "Sauvegarder le rapport", "", "Text Files (*.txt);;All Files (*)")
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(report_text)
                    QMessageBox.information(dialog, "Succès", f"Rapport sauvegardé avec succès.")
                except Exception as e:
                    QMessageBox.warning(dialog, "Erreur", f"Erreur lors de la sauvegarde : {e}")
        save_btn.clicked.connect(save_file)
        
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(dialog.accept)
        
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()

    # ========================== PANNEAU FICHIERS ==========================
    def _build_file_panel(self):
        panel = QWidget()
        v = QVBoxLayout(panel); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        header = QLabel("  EXPLORER"); header.setObjectName("PanelHeader")
        v.addWidget(header)

        self.pick_folder_btn = QPushButton("📂 Sélectionner un dossier…")
        self.pick_folder_btn.setObjectName("Accent")
        self.pick_folder_btn.clicked.connect(self.open_folder)
        v.addWidget(self.pick_folder_btn)

        self.path_label = QLabel("  Aucun dossier sélectionné")
        self.path_label.setObjectName("Muted"); self.path_label.setWordWrap(True)
        v.addWidget(self.path_label)

        self.whitelist_help = QLabel(
            "  ℹ️ Les cases cochées limitent l'ÉCRITURE : si aucune n'est cochée, "
            "tout le projet est modifiable.\n"
            "  ⚠️ La LECTURE reste possible sur tout le projet : ne travaille pas "
            "sur un dossier contenant des secrets non protégés (le contenu lu est "
            "envoyé au fournisseur du modèle)."
        )
        self.whitelist_help.setObjectName("Muted"); self.whitelist_help.setWordWrap(True)
        v.addWidget(self.whitelist_help)

        self.fs_model = CheckableFileSystemModel()

        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.setSpacing(4)
        
        self.check_all_btn = QPushButton("☑️ Tout")
        self.check_all_btn.clicked.connect(self.fs_model.check_all)
        btn_layout.addWidget(self.check_all_btn)
        
        self.uncheck_all_btn = QPushButton("🔲 Rien")
        self.uncheck_all_btn.clicked.connect(self.fs_model.uncheck_all)
        btn_layout.addWidget(self.uncheck_all_btn)
        
        self.graphify_btn = QPushButton("🚀 Graphify")
        self.graphify_btn.setToolTip("Générer le graphe de connaissances du projet")
        self.graphify_btn.clicked.connect(self.run_graphify)
        if self.app_mode != "coder":
            self.graphify_btn.hide()
        btn_layout.addWidget(self.graphify_btn)
        
        self.index_rag_btn = QPushButton("🧠 Index RAG")
        self.index_rag_btn.setToolTip("Construire l'index vectoriel RAG depuis graph.json")
        self.index_rag_btn.clicked.connect(self.run_index_rag)
        if self.app_mode != "coder":
            self.index_rag_btn.hide()
        btn_layout.addWidget(self.index_rag_btn)
        
        icons_layout = QHBoxLayout()
        icons_layout.setSpacing(4)
        
        self.view_graph_btn = QPushButton("👁️")
        self.view_graph_btn.setToolTip("Voir le fichier JSON brut (graph.json)")
        self.view_graph_btn.clicked.connect(self.show_graph_file)
        if self.app_mode != "coder":
            self.view_graph_btn.hide()
        icons_layout.addWidget(self.view_graph_btn)
        
        self.view_html_btn = QPushButton("🕸️")
        self.view_html_btn.setToolTip("Voir le graphe visuel interactif dans le navigateur")
        self.view_html_btn.clicked.connect(self.show_html_graph)
        if self.app_mode != "coder":
            self.view_html_btn.hide()
        icons_layout.addWidget(self.view_html_btn)
        
        self.callflow_html_btn = QPushButton("🗺️")
        self.callflow_html_btn.setToolTip("Générer et voir la carte interactive de l'architecture (Callflow HTML)")
        self.callflow_html_btn.clicked.connect(self.show_callflow_html)
        if self.app_mode != "coder":
            self.callflow_html_btn.hide()
        icons_layout.addWidget(self.callflow_html_btn)
        
        btn_layout.addLayout(icons_layout)
        
        self.analyse_graphify_btn = QPushButton("🧠 Analyse Graphify")
        self.analyse_graphify_btn.setToolTip("Générer GRAPH_REPORT.md à partir de graph.json via votre LLM")
        self.analyse_graphify_btn.clicked.connect(self.run_graphify_analysis)
        if self.app_mode != "coder":
            self.analyse_graphify_btn.hide()
        btn_layout.addWidget(self.analyse_graphify_btn)

        self.github_btn = QPushButton("🐙 GitHub")
        self.github_btn.setToolTip("Gérer le dépôt GitHub (Création ou Mise à jour)")
        self.github_btn.clicked.connect(self.run_github_helper)
        btn_layout.addWidget(self.github_btn)
        
        self.manual_graphify_btn = QPushButton("🕹️ Graphify Manuel")
        self.manual_graphify_btn.setToolTip("Ouvrir l'interface manuelle pour lancer graphify path, explain, query")
        self.manual_graphify_btn.clicked.connect(self.open_manual_graphify)
        if self.app_mode != "coder":
            self.manual_graphify_btn.hide()
        btn_layout.addWidget(self.manual_graphify_btn)
        
        v.addLayout(btn_layout)

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.fs_model)
        for col in (1, 2, 3):
            self.tree_view.setColumnHidden(col, True)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.clicked.connect(self.open_file_from_index)
        self.tree_view.hide()
        v.addWidget(self.tree_view)
        return panel

    # ========================== PANNEAU ÉDITEUR ==========================
    def _build_editor_panel(self):
        panel = QWidget()
        v = QVBoxLayout(panel); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        head = QFrame(); head.setObjectName("EditorHead")
        hh = QHBoxLayout(head); hh.setContentsMargins(10, 4, 10, 4)
        self.editor_label = QLabel("Aucun fichier ouvert")
        hh.addWidget(self.editor_label); hh.addStretch()
        self.save_btn = QPushButton("💾 Enregistrer")
        self.save_btn.clicked.connect(self.save_current_file)
        self.save_btn.setEnabled(False)
        hh.addWidget(self.save_btn)
        v.addWidget(head)

        self.editor = QPlainTextEdit(); self.editor.setObjectName("Editor")
        mono = QFont("Consolas"); mono.setStyleHint(QFont.StyleHint.Monospace); mono.setPointSize(11)
        self.editor.setFont(mono)
        self.editor.setPlaceholderText("Sélectionne un fichier dans l'explorateur pour l'afficher ici.")
        self.highlighter = PythonHighlighter(self.editor.document())
        v.addWidget(self.editor)
        return panel

    # =========================== PANNEAU CHAT ===========================
    def _build_chat_panel(self):
        panel = QWidget()
        v = QVBoxLayout(panel); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        head = QFrame(); head.setObjectName("EditorHead")
        hh = QHBoxLayout(head); hh.setContentsMargins(10, 4, 10, 4)
        hh.addWidget(QLabel("🤖 AGENT"))
        self.easter_egg_btn = QPushButton()
        self.easter_egg_btn.setFixedSize(10, 10)
        self.easter_egg_btn.setStyleSheet("background: transparent; border: none;")
        self.easter_egg_btn.clicked.connect(self.trigger_whip)
        hh.addWidget(self.easter_egg_btn)
        hh.addStretch()
        v.addWidget(head)

        self.chat_splitter = QSplitter(Qt.Orientation.Vertical)

        self.agents_frame = QFrame(); self.agents_frame.setObjectName("EditorHead")
        af = QVBoxLayout(self.agents_frame); af.setContentsMargins(8, 4, 8, 4); af.setSpacing(2)
        self.agents_header = QLabel("🧩 Sélection des Agents & IA")
        af.addWidget(self.agents_header)
        
        agents_scroll = QScrollArea(); agents_scroll.setWidgetResizable(True)
        agents_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.agents_container = QWidget()
        self.agents_container.setStyleSheet("background: transparent;")
        
        container_vbox = QVBoxLayout(self.agents_container)
        container_vbox.setContentsMargins(0, 0, 0, 0)
        container_vbox.setSpacing(6)
        
        self.core_agents_layout = QVBoxLayout()
        self.core_agents_layout.setSpacing(6)
        
        filtered_models = get_filtered_models(self.auth_mode)
        default_model = get_default_model(filtered_models)

        for agent_id, agent_data in AGENTS_CONFIG.items():
            row = QWidget()
            layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
            lbl = QLabel(agent_data.get("name", agent_id)); lbl.setFixedWidth(190)
            combo = QComboBox(); combo.addItems(filtered_models)
            agent_default_model = agent_data.get("default_model")
            if agent_default_model and agent_default_model in filtered_models:
                combo.setCurrentText(agent_default_model)
            elif default_model:
                combo.setCurrentText(default_model)
                
            cb = QCheckBox()
            is_active = agent_data.get("default_active", True)
            cb.setChecked(is_active)
            combo.setEnabled(is_active)
            lbl.setEnabled(is_active)
            
            cb.toggled.connect(combo.setEnabled)
            cb.toggled.connect(lbl.setEnabled)
            layout.addWidget(lbl); layout.addWidget(combo, 1); layout.addWidget(cb)
            self.core_agents_layout.addWidget(row)
            self.json_agents[agent_id] = {"combo": combo, "checkbox": cb}

        container_vbox.addLayout(self.core_agents_layout)
        
        self.dynamic_agents_sep = QFrame(); self.dynamic_agents_sep.setFrameShape(QFrame.Shape.HLine); self.dynamic_agents_sep.setStyleSheet("background-color: #3c3c3c;")
        self.dynamic_agents_sep.hide()
        container_vbox.addWidget(self.dynamic_agents_sep)
        
        self.agents_layout = QVBoxLayout()
        self.agents_layout.setSpacing(6)
        container_vbox.addLayout(self.agents_layout)
        container_vbox.addStretch()
        
        agents_scroll.setWidget(self.agents_container)
        af.addWidget(agents_scroll)
        

        
        self.chat_splitter.addWidget(self.agents_frame)

        self.chat_view = QTextEdit(); self.chat_view.setObjectName("Chat"); self.chat_view.setReadOnly(True)
        self.chat_view.document().setMaximumBlockCount(5000)
        self.chat_splitter.addWidget(self.chat_view)

        self.chat_splitter.setStretchFactor(0, 1)
        self.chat_splitter.setStretchFactor(1, 1)
        self.chat_splitter.setSizes([450, 150])
        v.addWidget(self.chat_splitter, 1)

        input_row = QFrame(); input_row.setObjectName("InputRow")
        ir = QVBoxLayout(input_row); ir.setContentsMargins(6, 6, 6, 6); ir.setSpacing(8)
        
        controls_hbox = QHBoxLayout(); controls_hbox.setContentsMargins(0, 0, 0, 0); controls_hbox.setSpacing(4)
        
        self.send_btn = QPushButton("➤"); self.send_btn.setObjectName("Accent"); self.send_btn.setFixedSize(40, 32)
        self.send_btn.clicked.connect(self.on_send_message)
        controls_hbox.addWidget(self.send_btn)

        self.retry_btn = QPushButton("🔄")
        self.retry_btn.setFixedSize(32, 32)
        self.retry_btn.setToolTip("Relancer la dernière mission")
        self.retry_btn.clicked.connect(self.on_retry_live_mission)
        self.retry_btn.setEnabled(False)
        controls_hbox.addWidget(self.retry_btn)

        self.recover_btn = QPushButton("♻️")
        self.recover_btn.setFixedSize(32, 32)
        self.recover_btn.setToolTip("Reprendre la session précédente")
        self.recover_btn.clicked.connect(self.on_recover_session)
        self.recover_btn.setEnabled(False)
        controls_hbox.addWidget(self.recover_btn)

        self.attach_btn_live = QPushButton("📎")
        self.attach_btn_live.setFixedSize(32, 32)
        self.attach_btn_live.setToolTip("Attacher une image")
        self.attach_btn_live.clicked.connect(self.on_attach_image_live)
        controls_hbox.addWidget(self.attach_btn_live)

        self.stop_btn = QPushButton("🛑")
        self.stop_btn.setFixedSize(32, 32)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.on_stop_live_agent)
        controls_hbox.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("🗑️")
        self.clear_btn.setFixedSize(32, 32)
        self.clear_btn.setToolTip("Nettoyer la zone de chat")
        self.clear_btn.clicked.connect(self.chat_view.clear)
        controls_hbox.addWidget(self.clear_btn)

        self.copy_btn = QPushButton("📋")
        self.copy_btn.setFixedSize(32, 32)
        self.copy_btn.setToolTip("Copier le log complet")
        self.copy_btn.clicked.connect(self.copy_chat_log)
        controls_hbox.addWidget(self.copy_btn)
        
        self.clean_mem_btn = QPushButton("🧹")
        self.clean_mem_btn.setFixedSize(32, 32)
        self.clean_mem_btn.setToolTip("Nettoyer les fichiers temporaires (.agent_memoire.md, etc.)")
        self.clean_mem_btn.clicked.connect(self.clean_agent_memory)
        controls_hbox.addWidget(self.clean_mem_btn)
        
        self.thinking_anim = DynamicThinkingAnimationWidget()
        self.thinking_anim.hide()
        controls_hbox.addWidget(self.thinking_anim)
        
        self.progress_bar_live = RealisticProgressBar()
        self.progress_bar_live.hide()
        controls_hbox.addWidget(self.progress_bar_live, 1)
        
        self.swarm_checkbox = QPushButton("🐝")
        self.swarm_checkbox.setFixedSize(32, 32)
        self.swarm_checkbox.setCheckable(True)
        self.swarm_checkbox.setToolTip("Mode Essaim (Désactivé)\nCliquer pour activer l'exécution parallèle.")
        self.swarm_checkbox.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3b3b3b;
            }
            QPushButton:!checked {
                color: #888;
                opacity: 0.5;
            }
            QPushButton:checked {
                background-color: rgba(255, 215, 0, 0.2);
                border: 1px solid #FFD700;
                color: white;
            }
        """)
        self.swarm_checkbox.toggled.connect(self._on_swarm_toggled)
        controls_hbox.addWidget(self.swarm_checkbox)
        
        self.demo_btn = QPushButton("🧪 Démo technique")
        self.demo_menu = QMenu()
        demo_sans = QAction("Démo Technique (Sans Essaim)", self)
        demo_sans.triggered.connect(lambda: self._run_demo(with_swarm=False))
        self.demo_menu.addAction(demo_sans)
        demo_avec = QAction("Démo Technique (Avec Essaim)", self)
        demo_avec.triggered.connect(lambda: self._run_demo(with_swarm=True))
        self.demo_menu.addAction(demo_avec)
        self.demo_btn.setMenu(self.demo_menu)
        controls_hbox.addWidget(self.demo_btn)
        
        if not getattr(self, 'is_demo', False):
            self.demo_btn.hide()
        
        # SÉCURITÉ (V4.0.1) : la case « Auto-approuver modifs » a été
        # SUPPRIMÉE. Elle court-circuitait la validation humaine des
        # écritures/suppressions sur les fichiers de la liste blanche —
        # la seule barrière effective contre une injection de prompt logée
        # dans le dépôt. On purge aussi l'ancien réglage persistant pour
        # qu'aucune valeur « collante » ne subsiste dans QSettings.
        self.settings.remove("auto_approve")
        
        controls_hbox.addStretch()
        
        ir.addLayout(controls_hbox)

        self.chat_input = ChatInputWidget(); self.chat_input.setObjectName("ChatInput")
        self.chat_input.setMinimumHeight(120)
        self.chat_input.setPlaceholderText("Décris ta mission à l'agent…")
        
        input_vbox = QVBoxLayout()
        input_vbox.setContentsMargins(0, 0, 0, 0); input_vbox.setSpacing(2)
        self.image_lbl_live = QLabel("")
        self.image_lbl_live.setObjectName("Muted")
        self.image_lbl_live.hide()
        input_vbox.addWidget(self.image_lbl_live)
        input_vbox.addWidget(self.chat_input, 1)
        ir.addLayout(input_vbox)
        
        self.chat_input.returnPressed.connect(self.on_send_message)
        self.chat_input.imagePasted.connect(self.on_image_pasted_live)
        
        v.addWidget(input_row)
        return panel

    def trigger_whip(self):
        self.whip_anim = WhipAnimationWidget(self.chat_view)
        self.whip_anim.show()

    def _build_generalist_panel(self):
        panel = QWidget()
        v = QVBoxLayout(panel); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        head = QFrame(); head.setObjectName("EditorHead")
        hh = QHBoxLayout(head); hh.setContentsMargins(10, 4, 10, 4)
        hh.addWidget(QLabel("💬 ASSISTANT GÉNÉRAL"))
        hh.addStretch()
        
        self.combo_generalist = QComboBox()
        filtered_models = get_filtered_models(self.auth_mode)
        self.combo_generalist.addItems(filtered_models)
        if filtered_models:
            self.combo_generalist.setCurrentText(get_default_model(filtered_models))
            
        hh.addWidget(self.combo_generalist)
        v.addWidget(head)

        self.chat_view_gen = QTextEdit(); self.chat_view_gen.setObjectName("Chat"); self.chat_view_gen.setReadOnly(True)
        self.chat_view_gen.document().setMaximumBlockCount(5000)
        v.addWidget(self.chat_view_gen, 1)

        input_row = QFrame(); input_row.setObjectName("InputRow")
        ir = QVBoxLayout(input_row); ir.setContentsMargins(6, 6, 6, 6); ir.setSpacing(8)
        
        controls_hbox = QHBoxLayout(); controls_hbox.setContentsMargins(0, 0, 0, 0); controls_hbox.setSpacing(4)
        
        self.send_btn_gen = QPushButton("➤"); self.send_btn_gen.setObjectName("Accent"); self.send_btn_gen.setFixedSize(40, 32)
        self.send_btn_gen.clicked.connect(self.on_send_message_gen)
        controls_hbox.addWidget(self.send_btn_gen)
        
        self.attach_btn_gen = QPushButton("📎")
        self.attach_btn_gen.setFixedSize(32, 32)
        self.attach_btn_gen.setToolTip("Attacher une image")
        self.attach_btn_gen.clicked.connect(self.on_attach_image_gen)
        controls_hbox.addWidget(self.attach_btn_gen)
        
        self.import_pdf_btn_gen = QPushButton("📄")
        self.import_pdf_btn_gen.setFixedSize(32, 32)
        self.import_pdf_btn_gen.setToolTip("Importer et convertir des PDF en JSON")
        self.import_pdf_btn_gen.clicked.connect(self.on_import_pdf_gen)
        controls_hbox.addWidget(self.import_pdf_btn_gen)

        
        self.stop_btn_gen = QPushButton("🛑")
        self.stop_btn_gen.setFixedSize(32, 32)
        self.stop_btn_gen.setEnabled(False)
        self.stop_btn_gen.clicked.connect(self.on_stop_gen_agent)
        controls_hbox.addWidget(self.stop_btn_gen)
        
        self.clear_btn_gen = QPushButton("🗑️")
        self.clear_btn_gen.setFixedSize(32, 32)
        self.clear_btn_gen.setToolTip("Nettoyer l'historique du chat")
        self.clear_btn_gen.clicked.connect(self.clear_gen_chat)
        controls_hbox.addWidget(self.clear_btn_gen)

        self.copy_btn_gen = QPushButton("📋")
        self.copy_btn_gen.setFixedSize(32, 32)
        self.copy_btn_gen.setToolTip("Copier le log complet")
        self.copy_btn_gen.clicked.connect(self.copy_gen_chat_log)
        controls_hbox.addWidget(self.copy_btn_gen)

        self.clean_mem_btn_gen = QPushButton("🧹")
        self.clean_mem_btn_gen.setFixedSize(32, 32)
        self.clean_mem_btn_gen.setToolTip("Nettoyer les fichiers temporaires (.agent_memoire.md, etc.)")
        self.clean_mem_btn_gen.clicked.connect(self.clean_agent_memory)
        controls_hbox.addWidget(self.clean_mem_btn_gen)

        self.thinking_anim_gen = EyeThinkingAnimationWidget()
        self.thinking_anim_gen.hide()
        controls_hbox.addWidget(self.thinking_anim_gen)
        
        self.progress_bar_gen = RealisticProgressBar()
        self.progress_bar_gen.hide()
        controls_hbox.addWidget(self.progress_bar_gen, 1)

        controls_hbox.addStretch()
        
        ir.addLayout(controls_hbox)

        self.chat_input_gen = ChatInputWidget(); self.chat_input_gen.setObjectName("ChatInput")
        self.chat_input_gen.setMinimumHeight(120)
        self.chat_input_gen.setPlaceholderText("Pose ta question ici (sans lien avec le code)...")
        
        input_vbox_gen = QVBoxLayout()
        input_vbox_gen.setContentsMargins(0, 0, 0, 0); input_vbox_gen.setSpacing(2)
        self.image_lbl_gen = QLabel("")
        self.image_lbl_gen.setObjectName("Muted")
        self.image_lbl_gen.hide()
        input_vbox_gen.addWidget(self.image_lbl_gen)
        input_vbox_gen.addWidget(self.chat_input_gen, 1)
        
        ir.addLayout(input_vbox_gen)
        
        self.chat_input_gen.returnPressed.connect(self.on_send_message_gen)
        self.chat_input_gen.imagePasted.connect(self.on_image_pasted_gen)
        
        v.addWidget(input_row)
        
        self.gen_history = []
        self.current_gen_response = ""
        
        return panel

    # ============================ FICHIERS ============================
    def open_folder(self, path=None):
        if path:
            directory = path
        else:
            directory = QFileDialog.getExistingDirectory(self, "Ouvrir le dossier projet")
            if not directory:
                return
        try:
            self.sandbox = FileSandbox(directory)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Dossier invalide : {e}")
            return
        self.project_root = directory
        self.save_directory = directory
        self.fs_model.setRootPath(directory)
        self.tree_view.setRootIndex(self.fs_model.index(directory))
        self.tree_view.show()
        self.pick_folder_btn.setText("📂 Changer de dossier…")
        self.path_label.setText("  " + directory)
        self.populate_agents(directory)
        self.add_system_message(f"📂 Dossier ouvert : {directory}")
        self._check_recovery_btn()
        
        last_mission_path = os.path.join(self.project_root, ".agent_last_mission.json")
        if os.path.exists(last_mission_path):
            try:
                import json
                with open(last_mission_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_live_mission = data.get("mission", "")
                    self.last_live_images = data.get("images", [])
                    if hasattr(self, 'retry_btn') and (self.last_live_mission or self.last_live_images):
                        self.retry_btn.setEnabled(True)
            except Exception:
                pass

        if self.app_mode == "hardware":
            reply = QMessageBox.question(self, "Import de Datasheets", 
                                         "Avez-vous des datasheets à importer pour ce projet ?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.import_datasheets(directory)

    def import_datasheets(self, directory):
        files, _ = QFileDialog.getOpenFileNames(self, "Sélectionner les datasheets (PDF)", "", "Fichiers PDF (*.pdf)")
        if not files:
            return
            
        try:
            import importlib.util
            import sys
            
            script_path = os.path.join(os.path.dirname(__file__), "hardware", "convertisseur PDF-Json.py")
            if not os.path.exists(script_path):
                QMessageBox.critical(self, "Erreur", "Le script 'convertisseur PDF-Json.py' est introuvable dans le dossier hardware.")
                return
                
            spec = importlib.util.spec_from_file_location("convertisseur_pdf_json", script_path)
            convertisseur = importlib.util.module_from_spec(spec)
            sys.modules["convertisseur_pdf_json"] = convertisseur
            spec.loader.exec_module(convertisseur)
            
            self.add_system_message("⏳ Importation et conversion des datasheets en cours...")
            QApplication.processEvents()
            
            convertisseur.process_multiple_pdfs(files, directory)
            
            self.add_system_message("✅ Datasheets importées et converties avec succès.")
            QMessageBox.information(self, "Succès", "L'importation et la conversion des datasheets sont terminées !")
        except Exception as e:
            self.add_system_message(f"❌ Erreur lors de la conversion des datasheets : {e}")
            QMessageBox.critical(self, "Erreur", f"Une erreur est survenue lors de la conversion :\n{e}")

    def populate_agents(self, directory):
        # BUGFIX CRITIQUE (V4.4.0) : agents_layout n'existe qu'en modes
        # Codeur/Hardware (_build_chat_panel). En mode Assistant Général,
        # « 📂 Ouvrir un dossier » crashait ici en AttributeError.
        if not hasattr(self, 'agents_layout'):
            return
        for i in reversed(range(self.agents_layout.count())):
            wdg = self.agents_layout.itemAt(i).widget()
            if wdg:
                wdg.setParent(None)
        self.project_agents = {}

        found = {}
        for sub in [".agents/rules", ".agents", ".claude/agents", "agents"]:
            d = os.path.join(directory, sub)
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if fn.lower().endswith(".md"):
                        name = os.path.splitext(fn)[0]
                        found.setdefault(name, os.path.join(d, fn))

        if not found:
            self.dynamic_agents_sep.hide()
            self.agents_header.setText("🧩 Sélection des Agents & IA")
            return
        
        self.dynamic_agents_sep.show()

        filtered_models = get_filtered_models(self.auth_mode)
        default_model = get_default_model(filtered_models)

        for name, path in sorted(found.items()):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            
            label = QLabel(name); label.setFixedWidth(190)
            combo = QComboBox(); combo.addItems(filtered_models)
            if default_model: combo.setCurrentText(default_model)
                
            cb = QCheckBox(); cb.setToolTip("Activer cet agent"); cb.setChecked(False)
            cb.toggled.connect(combo.setEnabled)
            cb.toggled.connect(label.setEnabled)
                
            row_layout.addWidget(label)
            row_layout.addWidget(combo, 1)
            row_layout.addWidget(cb)
            
            self.agents_layout.addWidget(row_widget)
            self.project_agents[name] = (cb, path, combo)

        self.agents_header.setText(f"🧩 Sélection des Agents & IA (+ {len(found)} du projet)")

    def get_active_agents_prompt(self):
        parts = []
        for name, agent_data in self.project_agents.items():
            cb = agent_data[0]
            path = agent_data[1]
            if cb.isChecked():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()[:4000]
                    parts.append(f"### Agent « {name} »\n{content}")
                except Exception:
                    pass
        if not parts: return ""
        return ("=== RÈGLES DES AGENTS ACTIVÉS ===\n"
                "Respecte les rôles et consignes suivants pendant toute la mission :\n\n"
                + "\n\n".join(parts)
                + "\n=== FIN DES RÈGLES D'AGENTS ===\n")

    def open_file_from_index(self, index):
        path = self.fs_model.filePath(index)
        self.open_file_path(path)

    def open_file_path(self, path):
        if not os.path.isfile(path):
            return
            
        # Check size before reading
        if os.path.getsize(path) > 2 * 1024 * 1024:
            self.editor.setPlainText(f"[Fichier trop volumineux (>2Mo). Lecture refusée.]")
            self.current_file = None
            self.save_btn.setEnabled(False)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            self.editor.setPlainText(f"[Fichier binaire non supporté ou encodage invalide]")
            self.current_file = None
            self.save_btn.setEnabled(False)
            return
        except Exception as e:
            self.editor.setPlainText(f"[Impossible d'afficher ce fichier : {e}]")
            self.current_file = None
            self.save_btn.setEnabled(False)
            return
            
        if self.current_file:
            self.file_watcher.removePath(self.current_file)
            
        self.current_file = path
        self.editor.setPlainText(content)
        self.editor_label.setText(os.path.basename(path))
        self.save_btn.setEnabled(True)
        self.file_watcher.addPath(path)
        if hasattr(self, 'left_tabs') and self.left_tabs.count() > 1:
            self.left_tabs.setCurrentIndex(1)

    def run_graphify_analysis(self):
        if not self.sandbox:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return

        api_key = None
        api_key_2 = None
        api_key_claude = None
        if self.auth_mode in ("api_key", "claude", "google_claude"):
            api_key = self.load_api_key(self.api_file_path, "Clé Principale")
            api_key_2 = self.load_api_key_2()
            api_key_claude = self.load_api_key_claude()
            
        lm_url = self.lm_url_input.text().strip() if self.auth_mode == "lm_studio" else None

        graph_path = os.path.join(self.sandbox.root, "graphify-out", "graph.json")
        report_path = os.path.join(self.sandbox.root, "graphify-out", "GRAPH_REPORT.md")

        if not os.path.exists(graph_path):
            QMessageBox.warning(self, "Erreur", "Le fichier graph.json est introuvable. Veuillez lancer Graphify d'abord.")
            return

        self.analysis_dialog = QDialog(self)
        self.analysis_dialog.setWindowTitle("🧠 Analyse Graphify")
        self.analysis_dialog.resize(800, 600)
        layout = QVBoxLayout(self.analysis_dialog)
        
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setPlainText("Génération du rapport GRAPH_REPORT.md en cours... Veuillez patienter.\n\n")
        layout.addWidget(self.analysis_text)
        
        self.analysis_dialog.show()

        # BUGFIX (V4.4.0) : accès direct à combo_generalist -> AttributeError
        # en mode Codeur (voir _general_model_name).
        model_name = self._general_model_name()

        self.analyse_graphify_btn.setEnabled(False)
        self.graphify_analysis_worker = GraphifyAnalysisWorker(
            self.auth_mode, api_key, model_name, graph_path, report_path, 
            lm_url=lm_url, api_key_2=api_key_2, api_key_claude=api_key_claude
        )
        self.graphify_analysis_worker.chunk_received.connect(self._on_graphify_analysis_chunk)
        self.graphify_analysis_worker.finished_analysis.connect(self._on_graphify_analysis_finished)
        self.graphify_analysis_worker.start()

    def _on_graphify_analysis_chunk(self, chunk):
        cursor = self.analysis_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.analysis_text.setTextCursor(cursor)
        self.analysis_text.ensureCursorVisible()

    def _on_graphify_analysis_finished(self, success, message):
        self.analyse_graphify_btn.setEnabled(True)
        cursor = self.analysis_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(message)
        self.analysis_text.setTextCursor(cursor)
        self.analysis_text.ensureCursorVisible()

    def show_graph_file(self):
        if not self.sandbox:
            return
        graph_path = os.path.join(self.sandbox.root, "graphify-out", "graph.json")
        if os.path.exists(graph_path):
            self.open_file_path(graph_path)
        else:
            QMessageBox.warning(self, "Erreur", "Le fichier graph.json est introuvable. Avez-vous lancé Graphify ?")

    def show_html_graph(self):
        if not self.sandbox: return
        import subprocess
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWidgets import QMessageBox
        
        graph_json = os.path.join(self.sandbox.root, "graphify-out", "graph.json")
        if not os.path.exists(graph_json):
            QMessageBox.warning(self, "Erreur", "Générez d'abord le graphe (Bouton 'Graphify').")
            return
            
        html_path1 = os.path.join(self.sandbox.root, "graphify-out", "graph.html")
        html_path2 = os.path.join(self.sandbox.root, "graphify-out", "GRAPH_TREE.html")
        
        reply = QMessageBox.question(self, "Choix de la vue",
            "Voulez-vous forcer la vue 'Méli-mélo' (Force-Directed Graph) ?\n"
            "⚠️ Sur un gros projet, cela peut faire ramer votre navigateur Web.\n\n"
            "Cliquez sur 'Non' pour ouvrir la vue 'Arbre' optimisée et bien rangée.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
            
        target_html = None
        self.view_html_btn.setText("⏳")
        QApplication.processEvents()
        
        # SÉCURITÉ (V4.3.0) : chemin ABSOLU du binaire résolu via le PATH de
        # l'application + env durci (jamais de nom nu avec cwd=projet, sinon
        # un 'graphify.exe' hostile déposé à la racine du dépôt serait lancé
        # sous Windows).
        graphify_bin = resolve_external_binary("graphify")
        if not graphify_bin:
            self.view_html_btn.setText("🕸️")
            QMessageBox.critical(self, "Erreur",
                                 "Binaire 'graphify' introuvable sur le PATH. "
                                 "Assurez-vous qu'il est installé.")
            return

        try:
            # ROBUSTESSE (V4.4.0) : ces subprocess n'avaient AUCUN timeout —
            # un binaire bloqué figeait l'interface indéfiniment.
            if reply == QMessageBox.StandardButton.Yes:
                env = hardened_subprocess_env()
                env["GRAPHIFY_VIZ_NODE_LIMIT"] = "30000"
                subprocess.run([graphify_bin, "cluster-only", "."], cwd=self.sandbox.root,
                               capture_output=True, env=env, timeout=180)
                if os.path.exists(html_path1):
                    target_html = html_path1
            else:
                subprocess.run([graphify_bin, "tree"], cwd=self.sandbox.root, capture_output=True,
                               env=hardened_subprocess_env(), timeout=180)
                if os.path.exists(html_path2):
                    target_html = html_path2
        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Erreur",
                                 "La génération du HTML a dépassé 180 s et a été interrompue.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de générer le HTML: {e}")
        finally:
            self.view_html_btn.setText("🕸️")
            
        if target_html:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target_html))
        else:
            QMessageBox.warning(self, "Erreur", "Le fichier HTML interactif n'a pas pu être trouvé ou généré.")

    def show_callflow_html(self):
        if not self.sandbox: return
        import subprocess
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWidgets import QMessageBox
        
        graph_json = os.path.join(self.sandbox.root, "graphify-out", "graph.json")
        if not os.path.exists(graph_json):
            QMessageBox.warning(self, "Erreur", "Générez d'abord le graphe (Bouton 'Graphify').")
            return
            
        self.callflow_html_btn.setText("⏳")
        QApplication.processEvents()
        
        graphify_bin = resolve_external_binary("graphify")
        if not graphify_bin:
            self.callflow_html_btn.setText("🗺️")
            QMessageBox.critical(self, "Erreur", "Binaire 'graphify' introuvable sur le PATH.")
            return

        try:
            subprocess.run([graphify_bin, "export", "callflow-html", "."], cwd=self.sandbox.root, capture_output=True, env=hardened_subprocess_env(), timeout=180)
            
            project_name = Path(self.sandbox.root).name
            html_path = os.path.join(self.sandbox.root, "graphify-out", f"{project_name}-callflow.html")
            
            if os.path.exists(html_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(html_path))
            else:
                QMessageBox.warning(self, "Erreur", "Le fichier HTML Callflow n'a pas pu être trouvé ou généré.")
        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Erreur", "La génération du Callflow HTML a dépassé 180 s et a été interrompue.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de générer le Callflow HTML: {e}")
        finally:
            self.callflow_html_btn.setText("🗺️")

    def save_current_file(self):
        if not self.current_file:
            return
        try:
            if self.sandbox:
                self.sandbox._backup_file(Path(self.current_file))
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self.editor.document().setModified(False)
            self.add_system_message(f"💾 Enregistré : {os.path.basename(self.current_file)}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Échec de l'enregistrement : {e}")

    def on_file_changed_externally(self, path):
        if path == self.current_file:
            self.reload_current_file()

    def reload_current_file(self):
        if self.current_file and os.path.isfile(self.current_file):
            if self.editor.document().isModified():
                reply = QMessageBox.question(
                    self, 'Modifications en cours',
                    "L'agent vient de modifier ce fichier mais vous avez des modifications non enregistrées dans l'éditeur.\nVoulez-vous recharger le fichier (et perdre vos modifications) ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.No:
                    return

            try:
                with open(self.current_file, "r", encoding="utf-8") as f:
                    self.editor.setPlainText(f.read())
                    self.editor.document().setModified(False)
            except Exception:
                pass

    # ============================ CHAT ============================
    @staticmethod
    def _esc(text):
        return (text.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;").replace("\n", "<br>"))

    def _safe_append(self, widget, html_text=None, plain_text=None):
        scrollbar = widget.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        old_value = scrollbar.value()

        if html_text is not None:
            widget.append(html_text)
        elif plain_text is not None:
            cursor = widget.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            widget.setTextCursor(cursor)
            widget.insertPlainText(plain_text)
            
        if not was_at_bottom:
            scrollbar.setValue(old_value)
        else:
            scrollbar.setValue(scrollbar.maximum())

    def copy_chat_log(self):
        QApplication.clipboard().setText(self.chat_view.toPlainText())
        self.add_system_message("📋 Log copié dans le presse-papiers.")

    def copy_gen_chat_log(self):
        QApplication.clipboard().setText(self.chat_view_gen.toPlainText())
        self._safe_append(self.chat_view_gen, html_text='<div style="color:#808080;font-style:italic;">📋 Log copié dans le presse-papiers.</div>')

    def _main_chat_widget(self):
        """Zone de chat où router les messages système.

        BUGFIX CRITIQUE (V4.4.0) : chat_view n'existe que si _build_chat_panel
        a été appelé (modes Codeur/Hardware). En mode Assistant Général,
        « 📂 Ouvrir un dossier » et le bouton 🧹 appelaient add_system_message
        -> AttributeError immédiate. On route vers chat_view_gen quand c'est
        la seule zone disponible, et on ne fait rien si aucune n'existe."""
        if hasattr(self, 'chat_view'):
            return self.chat_view
        if hasattr(self, 'chat_view_gen'):
            return self.chat_view_gen
        return None

    def add_user_message(self, text):
        widget = self._main_chat_widget()
        if widget is None:
            return
        self._safe_append(widget, html_text=
            '<div style="margin:8px 0;padding:8px 10px;background:#264f78;border-radius:8px;">'
            '<b style="color:#9cdcfe;">Vous</b><br>' + self._esc(text) + '</div>')

    def add_system_message(self, text):
        widget = self._main_chat_widget()
        if widget is None:
            return
        self._safe_append(widget, html_text=
            '<div style="margin:4px 0;color:#808080;font-style:italic;">' + self._esc(text) + '</div>')

    def add_agent_header(self):
        widget = self._main_chat_widget()
        if widget is None:
            return
        self._safe_append(widget, html_text='<div style="margin:8px 0 2px 0;"><b style="color:#dcdcaa;">Agent</b></div>')

    def append_to_console(self, text):
        widget = self._main_chat_widget()
        if widget is None:
            return
        self._safe_append(widget, plain_text=text)

    def on_agent_status(self, text):
        self.append_to_console(text)

    def clean_agent_memory(self):
        reply = QMessageBox.question(self, "Nettoyer l'environnement", 
                                     "Voulez-vous supprimer la mémoire de l'agent (.agent_memoire.md) et vider le cache ?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            import os
            # Nettoyer .agent_memoire.md
            if hasattr(self, 'project_root') and self.project_root:
                mem_file = os.path.join(self.project_root, ".agent_memoire.md")
                if os.path.exists(mem_file):
                    try:
                        os.remove(mem_file)
                    except Exception as e:
                        print(f"Erreur suppression {mem_file}: {e}")
                        
                import shutil
                docs_gen_dir = os.path.join(self.project_root, "docs_gen")
                auto_clean = self.settings.value("auto_clean_docs_gen", True, type=bool)
                if auto_clean and os.path.exists(docs_gen_dir):
                    try:
                        shutil.rmtree(docs_gen_dir)
                    except Exception as e:
                        print(f"Erreur suppression {docs_gen_dir}: {e}")
                        
                data_sheets_dir = os.path.join(self.project_root, "data_sheets")
                auto_clean_ds = self.settings.value("auto_clean_data_sheets", True, type=bool)
                if auto_clean_ds and os.path.exists(data_sheets_dir):
                    try:
                        shutil.rmtree(data_sheets_dir)
                    except Exception as e:
                        print(f"Erreur suppression {data_sheets_dir}: {e}")
                
                # Nettoyer aussi le __pycache__ si souhaité, etc. (optionnel)
                
                self.add_system_message("🧹 Fichiers temporaires et mémoire de l'agent nettoyés.")
                self._safe_append(self.chat_view, html_text='<div style="color: #6a9955;"><i>Environnement et mémoire nettoyés.</i></div>')

    def clear_gen_chat(self):
        self.chat_view_gen.clear()
        self.gen_history.clear()

    def on_send_message_gen(self):
        question = self.chat_input_gen.toPlainText().strip()
        if not question:
            return
            
        question = resolve_slash_command(question)
            
        api_key = None
        api_key_2 = None
        api_key_claude = None
        if self.auth_mode in ("api_key", "claude", "google_claude"):
            api_key = self.load_api_key(self.api_file_path, "Clé Principale")
            api_key_2 = self.load_api_key_2()
            api_key_claude = self.load_api_key_claude()
            if not any([api_key, api_key_2, api_key_claude]):
                QMessageBox.warning(self, "Erreur", "Sélectionne au moins un fichier de clé API valide.")
                return

        self._safe_append(self.chat_view_gen, html_text=
            '<div style="margin:8px 0;padding:8px 10px;background:#264f78;border-radius:8px;">'
            '<b style="color:#9cdcfe;">Vous</b><br>' + self._esc(question) + '</div>')
            
        msg_dict = {"role": "user", "content": question}
        if self.selected_images_gen:
            msg_dict["images"] = list(self.selected_images_gen)
            self.selected_images_gen.clear()
            self.image_lbl_gen.hide()
            self.image_lbl_gen.setText("")
            
        self.gen_history.append(msg_dict)
        self.chat_input_gen.clear()
        self._safe_append(self.chat_view_gen, html_text='<div style="margin:8px 0 2px 0;"><b style="color:#dcdcaa;">Assistant</b></div>')
        self.send_btn_gen.setEnabled(False)
        self.stop_btn_gen.setEnabled(True)

        model_name = self._general_model_name()
        lm_url = self.lm_url_input.text().strip() if hasattr(self, 'lm_url_input') else None
        
        self.gen_worker = SimpleChatWorker(
            self.auth_mode, api_key, self.gen_history.copy(), model_name, lm_url=lm_url,
            api_key_2=api_key_2, api_key_claude=api_key_claude
        )
        self.gen_worker.chunk_received.connect(self.append_to_gen_console)
        self.gen_worker.finished_chat.connect(self.on_gen_finished)
        
        self.current_gen_response = ""
        self.thinking_anim_gen.start_anim()
        self.progress_bar_gen.start_anim()
        if hasattr(self, 'node_graph'):
            self.node_graph.update_agent_state("assistant_general", "thinking")
        self.gen_worker.start()

    def append_to_gen_console(self, text):
        self.current_gen_response += text
        self._safe_append(self.chat_view_gen, plain_text=text)

    def on_gen_finished(self, success, error_msg):
        self.send_btn_gen.setEnabled(True)
        self.stop_btn_gen.setEnabled(False)
        self.thinking_anim_gen.stop_anim()
        self.progress_bar_gen.stop_anim()
        if hasattr(self, 'node_graph'):
            self.node_graph.update_agent_state("assistant_general", "idle")
            
        if success:
            self.gen_history.append({"role": "assistant", "content": self.current_gen_response})
        else:
            self.chat_view_gen.append(f'<div style="color:red;">❌ Erreur: {self._esc(error_msg)}</div>')

    # ============================ LANCEMENT ============================
    def on_image_pasted_gen(self, image):
        import tempfile, os
        fd, path = tempfile.mkstemp(prefix="pasted_img_", suffix=".png")
        os.close(fd)
        image.save(path, "PNG")
        self.selected_images_gen.append(path)
        names = [os.path.basename(f) for f in self.selected_images_gen]
        self.image_lbl_gen.setText("🖼️ " + ", ".join(names))
        self.image_lbl_gen.show()

    def on_image_pasted_live(self, image):
        import tempfile, os
        fd, path = tempfile.mkstemp(prefix="pasted_img_", suffix=".png")
        os.close(fd)
        image.save(path, "PNG")
        self.selected_images_live.append(path)
        names = [os.path.basename(f) for f in self.selected_images_live]
        self.image_lbl_live.setText("🖼️ " + ", ".join(names))
        self.image_lbl_live.show()

    def on_attach_image_gen(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Attacher des images", "", "Images (*.png *.jpg *.jpeg *.webp *.gif)")  # V4.4.0 : bmp retiré (non supporté par l'API Anthropic)
        if files:
            self.selected_images_gen.extend(files)
            names = [os.path.basename(f) for f in self.selected_images_gen]
            self.image_lbl_gen.setText("🖼️ " + ", ".join(names))
            self.image_lbl_gen.show()

    def on_import_pdf_gen(self):
        if not hasattr(self, 'project_root') or not self.project_root:
            QMessageBox.warning(self, "Erreur", "Veuillez d'abord ouvrir un dossier projet (en haut à gauche).")
            return

        files, _ = QFileDialog.getOpenFileNames(self, "Sélectionner les PDFs", "", "Fichiers PDF (*.pdf)")
        if not files:
            return
            
        try:
            import importlib.util
            import sys
            
            script_path = os.path.join(os.path.dirname(__file__), "hardware", "convertisseur PDF-Json.py")
            if not os.path.exists(script_path):
                QMessageBox.critical(self, "Erreur", "Le script 'convertisseur PDF-Json.py' est introuvable.")
                return
                
            spec = importlib.util.spec_from_file_location("convertisseur_pdf_json", script_path)
            convertisseur = importlib.util.module_from_spec(spec)
            sys.modules["convertisseur_pdf_json"] = convertisseur
            spec.loader.exec_module(convertisseur)
            
            self._safe_append(self.chat_view_gen, html_text='<div style="margin:8px 0;padding:8px 10px;background:#333;border-radius:8px;">⏳ <b>Système :</b> Importation et conversion des PDF en cours...</div>')
            QApplication.processEvents()
            
            convertisseur.process_multiple_pdfs(files, self.project_root, target_folder_name="docs_gen")
            
            self._safe_append(self.chat_view_gen, html_text='<div style="margin:8px 0;padding:8px 10px;background:#1e4d2b;border-radius:8px;">✅ <b>Système :</b> PDF convertis avec succès. Ils sont disponibles dans le dossier <code>docs_gen/</code>.</div>')
            
            msg_user = "Système : Des fichiers PDF ont été importés et convertis en JSON. Ils sont accessibles dans le sous-dossier 'docs_gen/' du projet courant. Tu pourras les utiliser avec l'outil de lecture de fichier si l'utilisateur te pose des questions à leur sujet."
            msg_assistant = "C'est noté. Je sais que des documents ont été importés dans le dossier 'docs_gen/'."
            self.gen_history.append({"role": "user", "content": msg_user})
            self.gen_history.append({"role": "assistant", "content": msg_assistant})
            
            QMessageBox.information(self, "Succès", "L'importation et la conversion des PDF sont terminées !")
        except Exception as e:
            self._safe_append(self.chat_view_gen, html_text=f'<div style="margin:8px 0;padding:8px 10px;background:#5a1919;border-radius:8px;">❌ <b>Erreur lors de la conversion :</b> {self._esc(str(e))}</div>')
            QMessageBox.critical(self, "Erreur", f"Une erreur est survenue :\n{e}")


    def on_attach_image_live(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Attacher des images", "", "Images (*.png *.jpg *.jpeg *.webp *.gif)")  # V4.4.0 : bmp retiré (non supporté par l'API Anthropic)
        if files:
            self.selected_images_live.extend(files)
            names = [os.path.basename(f) for f in self.selected_images_live]
            self.image_lbl_live.setText("🖼️ " + ", ".join(names))
            self.image_lbl_live.show()

    def _run_demo(self, with_swarm):
        # 1. Check or uncheck swarm mode
        self.swarm_checkbox.setChecked(with_swarm)
        
        # 2. Select Gemma 4 31B (Gemini API) for all agents
        target_model = "Gemma 4 31B (Gemini API)"
        
        # Check if the model is in the dropdowns (depends on auth_mode)
        # We just try to set it, if it fails, it will keep the default one or we can show a warning
        model_found = False
        
        # Core agents
        for agent_id, widgets in getattr(self, 'json_agents', {}).items():
            combo = widgets["combo"]
            index = combo.findText(target_model)
            if index >= 0:
                combo.setCurrentIndex(index)
                model_found = True
                
        # Project agents
        for name, agent_data in getattr(self, 'project_agents', {}).items():
            combo = agent_data[2]
            index = combo.findText(target_model)
            if index >= 0:
                combo.setCurrentIndex(index)
                model_found = True
                
        if not model_found:
            QMessageBox.warning(self, "Avertissement", f"Le modèle '{target_model}' n'est pas disponible avec le mode d'authentification actuel. La démonstration utilisera le modèle par défaut.")
            
        # 3. Pre-fill prompt
        if self.app_mode == "coder":
            if with_swarm:
                demo_prompt = "Développe un script Python complet pour un jeu de Snake. Le script doit utiliser pygame, inclure un système de score, des niveaux de difficulté qui augmentent la vitesse, gérer les collisions avec les murs et le corps, et sauvegarder le meilleur score dans un fichier JSON. Le code doit être structuré en classes (Game, Snake, Food), être bien commenté et inclure la gestion des erreurs."
            else:
                demo_prompt = "Écris un script Python qui calcule et affiche les 20 premiers nombres de la suite de Fibonacci."
        elif self.app_mode == "hardware":
            demo_prompt = "Crée un schéma SKIDL basique d'un diviseur de tension."
        else:
            demo_prompt = "Explique le fonctionnement de ce programme."
            
        self.chat_input.setPlainText(demo_prompt)
        
        # 4. Trigger send
        self.on_send_message()

    def on_send_message(self):
        mission = self.chat_input.toPlainText().strip()
        if not mission and not self.selected_images_live:
            return
            
        mission = resolve_slash_command(mission)
            
        self.last_live_mission = mission
        self.last_live_images = list(self.selected_images_live)
        
        if self.project_root:
            try:
                import json
                last_mission_path = os.path.join(self.project_root, ".agent_last_mission.json")
                with open(last_mission_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "mission": self.last_live_mission,
                        "images": self.last_live_images
                    }, f, indent=4)
            except Exception:
                pass
                
        if hasattr(self, 'retry_btn'):
            self.retry_btn.setEnabled(False)
            
        if not self.project_root:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet (bouton « Ouvrir un dossier »).")
            return
        api_key = None
        api_key_2 = None
        api_key_claude = None
        if self.auth_mode in ("api_key", "claude", "google_claude"):
            api_key = self.load_api_key(self.api_file_path, "Clé Principale")
            api_key_2 = self.load_api_key_2()
            api_key_claude = self.load_api_key_claude()
            if not any([api_key, api_key_2, api_key_claude]):
                QMessageBox.warning(self, "Erreur", "Sélectionne au moins un fichier de clé API valide.")
                return

        self.add_user_message(mission)
        self.chat_input.clear()
        self.add_agent_header()
        self.send_btn.setEnabled(False)
        if hasattr(self, 'recover_btn'):
            self.recover_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        images = []
        if self.selected_images_live:
            images = list(self.selected_images_live)
            self.selected_images_live.clear()
            self.image_lbl_live.hide()
            self.image_lbl_live.setText("")

        self.run_live_agent(mission, api_key, api_key_2, api_key_claude, images)

    def on_retry_live_mission(self):
        if hasattr(self, 'last_live_mission') and (self.last_live_mission or self.last_live_images):
            self.chat_input.setPlainText(self.last_live_mission)
            self.selected_images_live = list(self.last_live_images)
            if self.selected_images_live:
                names = [os.path.basename(f) for f in self.selected_images_live]
                self.image_lbl_live.setText("🖼️ " + ", ".join(names))
                self.image_lbl_live.show()
            self.on_send_message()

    def _check_recovery_btn(self):
        if hasattr(self, 'recover_btn') and self.project_root:
            recovery_path = os.path.join(self.project_root, ".agent_recovery.json")
            self.recover_btn.setEnabled(os.path.exists(recovery_path))

    def on_recover_session(self):
        if not self.project_root:
            return
        import json
        recovery_path = os.path.join(self.project_root, ".agent_recovery.json")
        if not os.path.exists(recovery_path):
            QMessageBox.warning(self, "Erreur", "Aucune session à reprendre n'a été trouvée.")
            return

        api_key = None
        api_key_2 = None
        api_key_claude = None
        if self.auth_mode in ("api_key", "claude", "google_claude"):
            api_key = self.load_api_key(self.api_file_path, "Clé Principale")
            api_key_2 = self.load_api_key_2()
            api_key_claude = self.load_api_key_claude()
            if not any([api_key, api_key_2, api_key_claude]):
                QMessageBox.warning(self, "Erreur", "Sélectionne au moins un fichier de clé API valide.")
                return

        try:
            with open(recovery_path, "r", encoding="utf-8") as f:
                recovery_data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible de lire la session de récupération :\n{e}")
            return

        mission = recovery_data.get("mission", "Mission restaurée")
        self.add_user_message(f"[REPRISE DE SESSION] {mission}")
        
        journal = recovery_data.get("mission_journal", [])
        if journal:
            summary_html = '<div style="margin:8px 0;padding:8px 10px;background:#2a2d2e;border-radius:8px;border-left:4px solid #0e639c;">'
            summary_html += '<b style="color:#4fc1ff;">Résumé des actions précédentes :</b><ul>'
            # BUGFIX CRITIQUE (V4.4.0) : mission_journal est une liste de
            # PAIRES (agent, résumé) — les tuples de _journal_add deviennent
            # des listes en JSON. L'ancien code faisait _esc(entry) sur une
            # LISTE -> AttributeError ('list' object has no attribute
            # 'replace') : la reprise de session plantait dès qu'au moins un
            # agent avait terminé avant le crash (le cas d'usage principal).
            for entry in journal:
                if isinstance(entry, (list, tuple)) and len(entry) == 2:
                    agent_name, text = entry
                    summary_html += (f"<li><b>{self._esc(str(agent_name))}</b> : "
                                     f"{self._esc(str(text))}</li>")
                else:
                    summary_html += f"<li>{self._esc(str(entry))}</li>"
            summary_html += "</ul></div>"
            widget = self._main_chat_widget()
            if widget is not None:
                self._safe_append(widget, html_text=summary_html)

        self.add_agent_header()
        self.send_btn.setEnabled(False)
        self.recover_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.run_live_agent(mission, api_key, api_key_2, api_key_claude, mission_images=None, recovery_data=recovery_data)

    def run_live_agent(self, mission, api_key, api_key_2=None, api_key_claude=None, mission_images=None, recovery_data=None):
        lm_url = self.lm_url_input.text().strip() if self.auth_mode == "lm_studio" else None
        
        active_agents = {}
        for agent_id, widgets in self.json_agents.items():
            active_agents[agent_id] = {
                "use": widgets["checkbox"].isChecked(),
                "model": AVAILABLE_MODELS[widgets["combo"].currentText()]
            }
        
        checked = list(self.fs_model.checked_paths) if self.fs_model else []
        unchecked = list(self.fs_model.unchecked_paths) if self.fs_model else []
        # BUGFIX (V4.4.0) : une liste VIDE (et non None) activait la liste
        # blanche avec zéro chemin autorisé -> toute écriture passait par le
        # flux anxiogène « hors liste blanche », alors que le texte d'aide
        # promet « si aucune n'est cochée, tout le projet est modifiable ».
        # Quand l'utilisateur n'a touché à AUCUNE case, la liste blanche est
        # désactivée (comportement documenté). Dès qu'une case est cochée OU
        # décochée, elle reste active (deny-wins conservé).
        if not checked and not unchecked:
            checked = None
            unchecked = None
        
        self.live_worker = LiveAgentWorker(
            self.auth_mode, api_key, mission, self.project_root,
            active_agents=active_agents,
            lm_url=lm_url,
            api_key_2=api_key_2,
            api_key_claude=api_key_claude,
            extra_rules=self.get_active_agents_prompt(),
            checked_paths=checked,
            unchecked_paths=unchecked,
            mission_images=mission_images,
            recovery_data=recovery_data,
            swarm_mode=getattr(self, 'swarm_checkbox', None) and self.swarm_checkbox.isChecked())
        self.live_worker.chunk_received.connect(self.append_to_console)
        self.live_worker.status_update.connect(self.on_agent_status)
        self.live_worker.agent_changed.connect(self.thinking_anim.set_agent)
        self.live_worker.finished_mission.connect(self.on_live_finished)
        self.live_worker.request_confirmation.connect(self.show_agent_confirmation)
        self.live_worker.request_user_input.connect(self.show_user_input_dialog)
        self.live_worker.final_diff.connect(self.show_final_diff_dialog)
        self.live_worker.data_flow_event.connect(self.node_graph.trigger_data_flow)
        self.live_worker.agent_state_changed.connect(self.node_graph.update_agent_state)
        self.live_worker.agent_action_event.connect(self.node_graph.show_agent_action)
        self.live_worker.agent_action_event.connect(self.on_agent_action_event)
        self.live_worker.agent_changed.connect(self.node_graph.set_agent_active)
        self.node_graph.reset_graph()
        self.agent_tool_usage = {}
        self.thinking_anim.start_anim()
        self.progress_bar_live.start_anim()
        self.live_worker.start()

    def _build_split_diff_widget(self, diff_text):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_edit = QTextEdit()
        left_edit.setReadOnly(True)
        right_edit = QTextEdit()
        right_edit.setReadOnly(True)
        
        left_html = ["<div style='font-family: monospace; white-space: pre-wrap; font-size: 13px;'>"]
        right_html = ["<div style='font-family: monospace; white-space: pre-wrap; font-size: 13px;'>"]
        
        buffer_removed = []
        buffer_added = []
        
        def flush_buffers():
            max_len = max(len(buffer_removed), len(buffer_added))
            for i in range(max_len):
                l = html.escape(buffer_removed[i]) if i < len(buffer_removed) else ""
                r = html.escape(buffer_added[i]) if i < len(buffer_added) else ""
                
                if l:
                    left_html.append(f"<div style='background-color: #4a2323; color: #ff8b8b;'>- {l}</div>")
                else:
                    left_html.append("<div style='background-color: transparent; color: transparent;'>-</div>")
                    
                if r:
                    right_html.append(f"<div style='background-color: #234a23; color: #8bff8b;'>+ {r}</div>")
                else:
                    right_html.append("<div style='background-color: transparent; color: transparent;'>+</div>")
            
            buffer_removed.clear()
            buffer_added.clear()

        for line in diff_text.split('\n'):
            if line.startswith('=== ') or line.startswith('---') or line.startswith('+++') or line.startswith('[STATISTIQUES'):
                flush_buffers()
                if line.startswith('=== '):
                    h_line = f"<br><div style='font-weight: bold; color: #e5e510;'>{html.escape(line)}</div>"
                else:
                    h_line = f"<div style='font-weight: bold; color: #569cd6;'>{html.escape(line)}</div>"
                left_html.append(h_line)
                right_html.append(h_line)
            elif line.startswith('@@'):
                flush_buffers()
                h_line = f"<div style='background-color: #2b3a42; color: #4fc1ff;'>{html.escape(line)}</div>"
                left_html.append(h_line)
                right_html.append(h_line)
            elif line.startswith('-'):
                buffer_removed.append(line[1:])
            elif line.startswith('+'):
                buffer_added.append(line[1:])
            else:
                flush_buffers()
                ctx_line = line[1:] if line.startswith(' ') else line
                c_line = f"<div style='color: #d4d4d4;'>  {html.escape(ctx_line)}</div>"
                left_html.append(c_line)
                right_html.append(c_line)
        
        flush_buffers()
        
        left_html.append("</div>")
        right_html.append("</div>")
        
        left_edit.setHtml("".join(left_html))
        right_edit.setHtml("".join(right_html))
        
        left_layout = QVBoxLayout()
        lbl_avant = QLabel("<b>Avant</b>")
        lbl_avant.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(lbl_avant)
        left_layout.addWidget(left_edit)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        
        right_layout = QVBoxLayout()
        lbl_apres = QLabel("<b>Après</b>")
        lbl_apres.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(lbl_apres)
        right_layout.addWidget(right_edit)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        
        return splitter

    def show_user_input_dialog(self, question):
        dialog = QDialog(self)
        dialog.setWindowTitle("Question de l'agent")
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.resize(500, 300)
        
        layout = QVBoxLayout(dialog)
        
        lbl = QLabel(question + "\n\nVotre réponse:")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        
        text_edit = ImageDropTextEdit()
        layout.addWidget(text_edit)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(btn_box)
        
        def on_finished(result):
            if self.live_worker:
                text = text_edit.toPlainText() if result == QDialog.DialogCode.Accepted else ""
                images = text_edit.pasted_images if result == QDialog.DialogCode.Accepted else []
                self.live_worker.provide_user_input(text, images)
                
        dialog.finished.connect(on_finished)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        
        self._current_input_dialog = dialog
        dialog.show()

    def show_agent_confirmation(self, message):
        dialog = QDialog(self)
        dialog.setWindowTitle("Confirmation requise")
        dialog.resize(1000, 700)
        layout = QVBoxLayout(dialog)
        
        if "Diff:\n" in message:
            parts = message.split("Diff:\n", 1)
            question_part = parts[0].strip()
            diff_part = parts[1]
            
            autoriser_idx = diff_part.rfind("Autoriser ?")
            if autoriser_idx != -1:
                diff_text = diff_part[:autoriser_idx].strip()
                question_part += "\n\nAutoriser ?"
            else:
                diff_text = diff_part.strip()
            
            lbl_question = QLabel(html.escape(question_part).replace('\n', '<br>'))
            lbl_question.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px; background-color: #2d2d30; color: #d4d4d4; border-radius: 5px;")
            lbl_question.setWordWrap(True)
            layout.addWidget(lbl_question)
            
            splitter = self._build_split_diff_widget(diff_text)
            layout.addWidget(splitter)
        else:
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            
            html_msg = html.escape(message)
            html_msg = html_msg.replace('\n', '<br>')
            
            lines = html_msg.split('<br>')
            styled_lines = []
            for line in lines:
                if line.startswith('-'):
                    styled_lines.append(f'<span style="color:#d16969;">{line}</span>')
                elif line.startswith('+'):
                    styled_lines.append(f'<span style="color:#89d185;">{line}</span>')
                elif line.startswith('@@'):
                    styled_lines.append(f'<span style="color:#569cd6;">{line}</span>')
                else:
                    styled_lines.append(line)
                    
            text_edit.setHtml('<br>'.join(styled_lines))
            layout.addWidget(text_edit)
            
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        layout.addWidget(btn_box)
        
        def on_finished(result):
            if self.live_worker:
                self.live_worker.provide_confirmation(result == QDialog.DialogCode.Accepted)
                
        dialog.finished.connect(on_finished)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        self._current_confirm_dialog = dialog
        dialog.show()

    def show_final_diff_dialog(self, diff_text):
        dialog = QDialog(self)
        dialog.setWindowTitle("Bilan des Modifications (Avant / Après)")
        dialog.resize(900, 700)
        layout = QVBoxLayout(dialog)
        
        lbl = QLabel("La mission est terminée. Voici le récapitulatif des modifications effectuées sur vos fichiers :")
        layout.addWidget(lbl)
        
        splitter = self._build_split_diff_widget(diff_text)
        layout.addWidget(splitter)
        
        # Bouton de restauration : annule TOUTES les modifications de la
        # mission en réécrivant les snapshots pris avant chaque première
        # modification (workers.LiveAgentWorker.restore_mission_changes).
        btn_row = QHBoxLayout()
        restore_btn = QPushButton("⏪ Tout annuler (restaurer l'état initial)")
        restore_btn.setToolTip("Restaure tous les fichiers modifiés pendant la mission "
                               "à leur état d'avant-mission. Les fichiers créés seront supprimés.")

        def do_restore():
            confirm = QMessageBox.question(
                dialog, "Restaurer l'état initial",
                "Annuler TOUTES les modifications de cette mission ?\n\n"
                "• Les fichiers modifiés retrouveront leur contenu d'avant-mission.\n"
                "• Les fichiers créés pendant la mission seront supprimés.\n"
                "(Des sauvegardes restent disponibles dans .agent_backups.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if confirm != QMessageBox.StandardButton.Yes:
                return
            if not (hasattr(self, 'live_worker') and self.live_worker):
                QMessageBox.warning(dialog, "Restauration", "Aucune mission à restaurer.")
                return
            report = self.live_worker.restore_mission_changes()
            restore_btn.setEnabled(False)
            restore_btn.setText("⏪ État initial restauré")
            self.reload_current_file()
            self.add_system_message("⏪ Modifications de la mission annulées :\n" + report)
            QMessageBox.information(dialog, "Restauration terminée", report)

        restore_btn.clicked.connect(do_restore)
        btn_row.addWidget(restore_btn)
        btn_row.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dialog.accept)
        btn_row.addWidget(btn_box)
        layout.addLayout(btn_row)
        
        dialog.exec()

    # ======================== CONNEXION / MODÈLES ========================
    def browse_api_file_2(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner la clé API n°2 (forfait payant)", "",
            "Fichiers texte (*.txt);;Tous les fichiers (*)")
        if file_name:
            self.api_file_path_2 = file_name
            self.settings.setValue("api_file_path_2", file_name)
            self.api_file_input2.setText(os.path.basename(file_name))

    def clear_api_file_2(self):
        self.api_file_path_2 = ""
        self.settings.setValue("api_file_path_2", "")
        self.api_file_input2.setText("(optionnelle)")
        print("[ℹ️ INFO] Clé 2 effacée (tous les modèles utiliseront la Clé 1).")

    def browse_api_file_claude(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Sélectionner la clé Claude (Optionnelle)", "", "Text Files (*.txt);;All Files (*)")
        if file_name:
            self.api_file_path_claude = file_name
            self.settings.setValue("api_file_path_claude", file_name)
            self.api_file_input_claude.setText(os.path.basename(file_name))
            print(f"[✅ SUCCÈS] Clé Claude enregistrée : {file_name}")

    def clear_api_file_claude(self):
        self.api_file_path_claude = ""
        self.settings.setValue("api_file_path_claude", "")
        self.api_file_input_claude.setText("(optionnelle)")
        print("[ℹ️ INFO] Clé Claude effacée.")

    def load_api_key_2(self):
        # Renvoie la clé 2 en mémoire si renseignée.
        # N'affiche un warning que si elle est censée être utilisée par un modèle.
        if self.auth_mode not in ("api_key", "google_claude") or not getattr(self, 'api_file_path_2', None):
            return None
        key2 = self.load_api_key(self.api_file_path_2, "Clé 2")
        return key2

    def load_api_key_claude(self):
        if self.auth_mode != "google_claude" or not getattr(self, 'api_file_path_claude', None):
            return None
        key_claude = self.load_api_key(self.api_file_path_claude, "Clé Claude")
        return key_claude

    def browse_api_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner la clé API", "", "Fichiers texte (*.txt);;Tous les fichiers (*)")
        if file_name:
            self.api_file_path = file_name
            # BUGFIX : le chemin n'était jamais sauvegardé -> à chaque lancement
            # il fallait re-sélectionner le fichier de clé.
            # V4.4.0 : réglage distinct par mode (Google vs Claude).
            self.settings.setValue(self._api_key_setting, file_name)
            self.api_file_input.setText(os.path.basename(file_name))

    def load_api_key(self, filename, key_name="Clé"):
        try:
            if filename and os.path.exists(filename):
                # Avertissement (POSIX) si le fichier de clé est lisible par
                # d'autres utilisateurs de la machine. Idéalement, utiliser un
                # trousseau système (module 'keyring') plutôt qu'un fichier.
                if os.name == "posix":
                    try:
                        mode = os.stat(filename).st_mode
                        if mode & (stat.S_IRGRP | stat.S_IROTH):
                            logger.warning(
                                f"[SÉCURITÉ] Le fichier de clé API '{filename}' est lisible "
                                f"par d'autres utilisateurs. Recommandé : chmod 600 \"{filename}\"")
                    except OSError:
                        pass
                with open(filename, "r", encoding="utf-8") as f:
                    for line in f:
                        key = line.strip()
                        if key:
                            if any(c.isspace() for c in key):
                                print(f"[❌ ERREUR - load_api_key] La {key_name} est invalide (espaces).", file=sys.stderr)
                                return None
                            print(f"[✅ SUCCÈS] {key_name} chargée depuis : {filename}")
                            return key
            return None
        except Exception as e:
            print(f"[❌ ERREUR - load_api_key] Impossible de lire la {key_name} : {e}", file=sys.stderr)
            return None

    def _general_model_name(self):
        """ID du modèle « généraliste » à utiliser.

        BUGFIX CRITIQUE (V4.4.0) : combo_generalist n'existe QUE dans le
        panneau du mode Assistant Général (_build_generalist_panel). Les
        boutons « 🧪 Tester » (toolbar, tous modes) et « 🧠 Analyse Graphify »
        (mode Codeur !) y accédaient directement -> AttributeError garantie
        en modes Codeur et Hardware. On retombe désormais sur le modèle par
        défaut du mode de connexion courant quand le widget n'existe pas."""
        if hasattr(self, 'combo_generalist'):
            key = self.combo_generalist.currentText()
            return AVAILABLE_MODELS.get(key, key)
        filtered = get_filtered_models(self.auth_mode)
        default_key = get_default_model(filtered)
        return AVAILABLE_MODELS.get(default_key, default_key)

    def get_selected_models(self):
        models = []
        if hasattr(self, 'json_agents'):
            for agent_id, widgets in self.json_agents.items():
                if widgets["checkbox"].isChecked():
                    models.append(AVAILABLE_MODELS[widgets["combo"].currentText()])
        return list(set(models))

    def test_connection(self):
        api_key = None
        api_key_2 = None
        api_key_claude = None
        lm_url = None
        if self.auth_mode in ("api_key", "claude", "google_claude"):
            api_key = self.load_api_key(self.api_file_path, "Clé Principale")
            api_key_2 = self.load_api_key_2()
            api_key_claude = self.load_api_key_claude()
            if not any([api_key, api_key_2, api_key_claude]):
                QMessageBox.warning(self, "Erreur", "Sélectionne au moins un fichier de clé API valide.")
                return
        models_to_test = self.get_selected_models()
        # BUGFIX (V4.4.0) : accès direct à combo_generalist -> AttributeError
        # en modes Codeur et Hardware (voir _general_model_name).
        gen_m = self._general_model_name()
        if gen_m:
            models_to_test.append(gen_m)
        
        self.test_btn.setEnabled(False)
        self.test_btn.setText("⏳…")
        lm_url = self.lm_url_input.text().strip() if self.auth_mode == "lm_studio" else None
        self.test_worker = TestKeyWorker(self.auth_mode, api_key, models_to_test, lm_url=lm_url,
                                         api_key_2=api_key_2, api_key_claude=api_key_claude)
        self.test_worker.result_signal.connect(self.on_test_finished)
        self.test_worker.start()

    def on_test_finished(self, success, message):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("🧪 Tester")
        if success:
            QMessageBox.information(self, "Succès", message)
        else:
            QMessageBox.critical(self, "Erreur", message)

    # ============================ FIN DE TÂCHE ============================
    def on_live_finished(self, success, message):
        self.send_btn.setEnabled(True)
        if hasattr(self, 'retry_btn') and hasattr(self, 'last_live_mission') and (self.last_live_mission or self.last_live_images):
            self.retry_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.thinking_anim.stop_anim()
        self.progress_bar_live.stop_anim()
        if getattr(self, '_graphify_build_worker', None) and self._graphify_build_worker.isRunning():
            self._graphify_build_worker.cancel()
            self._graphify_build_worker.wait()

    def on_agent_action_event(self, agent_id, action_name, target):
        pass

    def _on_swarm_toggled(self, state):
        is_checked = (state == 2) or (state is True)
        
        if is_checked:
            self.swarm_checkbox.setToolTip("Mode Essaim (Activé)\nCliquer pour désactiver l'exécution parallèle.")
            if self.auth_mode != "lm_studio":
                QMessageBox.warning(
                    self,
                    "Attention : Surcoût de tokens",
                    "Vous venez d'activer le Mode Essaim (Parallélisme).\n\n"
                    "⚠️ ATTENTION : Vous n'utilisez pas un modèle local gratuit.\n"
                    "Le lancement de plusieurs agents simultanément multiplie le contexte envoyé à l'API. Cela risque de consommer **significativement plus de tokens** (et donc de générer un coût plus élevé) qu'une exécution classique.\n\n"
                    "Veuillez en tenir compte pour vos limites de facturation."
                )
        else:
            self.swarm_checkbox.setToolTip("Mode Essaim (Désactivé)\nCliquer pour activer l'exécution parallèle.")

    def _update_memory_ui(self):
        self.reload_current_file()
        self.add_system_message(message if success else f"❌ {message}")
        self._check_recovery_btn()
        
        if success:
            git_dir = os.path.join(self.project_root, ".git")
            if os.path.isdir(git_dir):
                QMessageBox.information(
                    self, "Mise à jour Git requise",
                    "La mission est terminée.\n\nCe projet utilise Git (.git détecté).\n"
                    "N'oubliez pas de faire votre 'git add' et 'git commit' !\n\n"
                    "Si l'agent a préparé un message, il se trouve dans le résumé de la mission."
                )

    def on_stop_live_agent(self):
        if hasattr(self, 'live_worker') and self.live_worker and self.live_worker.isRunning():
            self.live_worker.cancel()
            self.stop_btn.setEnabled(False)
            self.thinking_anim.stop_anim()
            self.progress_bar_live.stop_anim()
            self.add_system_message("🛑 Arrêt demandé... Interruption en cours.")
            QTimer.singleShot(1000, self._check_recovery_btn)

    def on_stop_gen_agent(self):
        if hasattr(self, 'gen_worker') and self.gen_worker and self.gen_worker.isRunning():
            self.gen_worker.cancel()
            self.stop_btn_gen.setEnabled(False)
            self.thinking_anim_gen.stop_anim()
            self.progress_bar_gen.stop_anim()
            self.chat_view_gen.append('<div style="margin:4px 0;color:#808080;font-style:italic;">🛑 Arrêt demandé... Interruption en cours.</div>')

    def show_agent_details(self, agent_id):
        history = []
        if hasattr(self, 'live_worker') and self.live_worker:
            history = self.live_worker.agent_histories.get(agent_id, [])
        
        if hasattr(self, '_agent_overlay') and self._agent_overlay:
            self._agent_overlay.setParent(None)
            self._agent_overlay.deleteLater()
            
        overlay = QFrame(self.node_graph)
        overlay.setObjectName("AgentOverlay")
        overlay.setStyleSheet("""
            QFrame#AgentOverlay {
                background-color: rgba(35, 35, 40, 240);
                border: 1px solid #569cd6;
                border-radius: 8px;
            }
            QLabel { background: transparent; }
            QLabel#AgentTitle { font-size: 16px; font-weight: bold; color: #569cd6; }
            QLabel#SectionTitle { font-size: 13px; font-weight: bold; color: #dcdcaa; margin-top: 10px; margin-bottom: 5px; }
        """)
        
        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)
        
        header_layout = QHBoxLayout()
        title = QLabel(f"🤖 Agent : {agent_id}")
        title.setObjectName("AgentTitle")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("QPushButton { background: transparent; border: none; color: #858585; font-size: 16px; font-weight: bold; padding: 0px; } QPushButton:hover { color: #ffffff; background: #c53030; border-radius: 14px; }")
        close_btn.clicked.connect(overlay.hide)
        header_layout.addWidget(close_btn)
        
        layout.addLayout(header_layout)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: rgba(0, 0, 0, 0.2); width: 10px; border-radius: 5px; margin: 0px; }
            QScrollBar::handle:vertical { background: #569cd6; border-radius: 5px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #4ea8ea; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 10, 0)
        scroll_layout.setSpacing(6)
        
        if agent_id in AGENTS_CONFIG:
            role = AGENTS_CONFIG[agent_id].get('role', 'Non défini')
            goal = AGENTS_CONFIG[agent_id].get('goal', 'Non défini')
            
            role_lbl = QLabel(f"🎭 <b>Rôle :</b> {role}")
            role_lbl.setWordWrap(True)
            role_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            scroll_layout.addWidget(role_lbl)
            
            if goal and goal != 'Non défini':
                goal_lbl = QLabel(f"🎯 <b>Objectif :</b> {goal}")
                goal_lbl.setWordWrap(True)
                goal_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                scroll_layout.addWidget(goal_lbl)
            
        # Calcul des statistiques et métriques
        nb_fichiers_modifies = 0
        nb_commandes = 0
        nb_delegations = 0
        total_chars = 0
        
        last_thought = ""
        
        # Pour les communications :
        a_parle_a = set()
        a_recu_de = set()
        
        # Parcourir les historiques des autres agents pour voir s'ils ont délégué à celui-ci
        all_histories = {}
        if hasattr(self, 'live_worker') and self.live_worker:
            if hasattr(self.live_worker, 'full_agent_histories'):
                all_histories = self.live_worker.full_agent_histories
            elif hasattr(self.live_worker, 'agent_histories'):
                all_histories = self.live_worker.agent_histories
                
        for a_id, a_hist in all_histories.items():
            for msg in a_hist:
                if msg.get("role") == "assistant":
                    content = str(msg.get("content", ""))
                    if '"action"' in content and '"delegate"' in content:
                        if f'"agent": "{agent_id}"' in content or f'"agent":"{agent_id}"' in content:
                            if a_id != agent_id:
                                a_recu_de.add(a_id)
        
        modified_files = set()
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = str(content)
                
            total_chars += len(content)
            
            if role == "assistant":
                if '"action"' in content:
                    if any(cmd in content for cmd in ["write_file", "replace_file_content", "multi_replace_file_content", "edit_file", "append_file", "create_file"]):
                        nb_fichiers_modifies += 1
                        paths = re.findall(r'"path"\s*:\s*"([^"]+)"', content)
                        paths += re.findall(r'"TargetFile"\s*:\s*"([^"]+)"', content)
                        paths += re.findall(r'"target_file"\s*:\s*"([^"]+)"', content)
                        paths += re.findall(r'"file"\s*:\s*"([^"]+)"', content)
                        for p in paths:
                            modified_files.add(p)
                    
                    if "run_command" in content or "run_named_command" in content:
                        nb_commandes += 1
                    
                    if '"delegate"' in content:
                        nb_delegations += 1
                        m = re.search(r'"agent"\s*:\s*"([^"]+)"', content)
                        if m:
                            tgt = m.group(1)
                            if tgt != agent_id:
                                a_parle_a.add(tgt)
                
                # Extraction de la dernière pensée
                thought_match = re.search(r'<thought>(.*?)</thought>', content, re.DOTALL | re.IGNORECASE)
                if thought_match:
                    last_thought = thought_match.group(1).strip()
                else:
                    text_before = re.sub(r'```(?:json)?\s*\{.*?\}\s*```', '', content, flags=re.DOTALL).strip()
                    if text_before and not text_before.startswith('{'):
                        last_thought = text_before
                        
        tokens_estimes = total_chars // 4

        # 1. Action Rapide: Demander un résumé
        btn_layout = QHBoxLayout()
        summary_btn = QPushButton("📝 Demander un résumé")
        summary_btn.setStyleSheet("QPushButton { background: #0e639c; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; border: none; } QPushButton:hover { background: #1177bb; }")
        
        def ask_summary(*args):
            if hasattr(self, 'live_worker') and self.live_worker:
                msg = {"role": "user", "content": "[DIRECTIVE EXPLICITE] Fais un résumé concis de ce que tu as accompli jusqu'ici, où tu en es, et ce qu'il te reste à faire."}
                if hasattr(self.live_worker, 'agent_histories'):
                    self.live_worker.agent_histories.setdefault(agent_id, []).append(msg)
                if hasattr(self.live_worker, 'full_agent_histories'):
                    self.live_worker.full_agent_histories.setdefault(agent_id, []).append(msg)
                self.add_system_message(f"✉️ <b>Demande de résumé envoyée à {agent_id}.</b>")
                summary_btn.setText("✅ Demande envoyée")
                QTimer.singleShot(2000, lambda: summary_btn.setText("📝 Demander un résumé"))
                
        summary_btn.clicked.connect(ask_summary)
        btn_layout.addWidget(summary_btn)
        btn_layout.addStretch()
        scroll_layout.addLayout(btn_layout)
        
        # 2. Statistiques et Métriques
        stats_title = QLabel("📊 Métriques de Session")
        stats_title.setObjectName("SectionTitle")
        scroll_layout.addWidget(stats_title)
        
        stats_text = f"""
        <ul style='margin-top: 5px; margin-bottom: 10px; padding-left: 20px; color: #d4d4d4;'>
            <li><b>Fichiers modifiés :</b> {len(modified_files)} fichier(s) unique(s) <i>({nb_fichiers_modifies} action(s))</i></li>
            <li><b>Commandes exécutées :</b> {nb_commandes}</li>
            <li><b>Délégations :</b> {nb_delegations}</li>
            <li><b>Jetons (tokens) estimés :</b> ~{tokens_estimes}</li>
        </ul>
        """
        stats_lbl = QLabel(stats_text)
        stats_lbl.setWordWrap(True)
        scroll_layout.addWidget(stats_lbl)
        
        # 2.5 Outils utilisés
        tools_title = QLabel("🛠️ Outils utilisés")
        tools_title.setObjectName("SectionTitle")
        scroll_layout.addWidget(tools_title)
        
        node_tools = {}
        if hasattr(self, 'node_graph') and agent_id in self.node_graph.nodes:
            node_tools = getattr(self.node_graph.nodes[agent_id], 'used_tools', {})
            
        if node_tools:
            tools_lines = [f"<li><b>{t}</b> : {c} fois</li>" for t, c in sorted(node_tools.items(), key=lambda x: x[1], reverse=True)]
            tools_text = f"<ul style='margin-top: 5px; margin-bottom: 10px; padding-left: 20px; color: #d4d4d4;'>" + "".join(tools_lines) + "</ul>"
        else:
            tools_text = "<i style='color: #888; margin-top: 5px; margin-bottom: 10px; display: block;'>Aucun outil utilisé.</i>"
            
        tools_lbl = QLabel(tools_text)
        tools_lbl.setWordWrap(True)
        scroll_layout.addWidget(tools_lbl)
        
        # 3. Réseau de communication
        comm_title = QLabel("🔄 Réseau de communication")
        comm_title.setObjectName("SectionTitle")
        scroll_layout.addWidget(comm_title)
        
        comm_lines = []
        if a_recu_de:
            comm_lines.append(f"<span style='color: #4ec9b0;'>⬅️ A reçu des directives de :</span> <b>{', '.join(a_recu_de)}</b>")
        if a_parle_a:
            comm_lines.append(f"<span style='color: #ce9178;'>➡️ A délégué à :</span> <b>{', '.join(a_parle_a)}</b>")
            
        if not comm_lines:
            comm_lines.append("<i style='color: #888;'>Aucune communication détectée.</i>")
            
        comm_lbl = QLabel("<div style='margin-top: 5px; margin-bottom: 10px; color: #d4d4d4;'>" + "<br>".join(comm_lines) + "</div>")
        comm_lbl.setWordWrap(True)
        scroll_layout.addWidget(comm_lbl)
        
        # 4. Monologue Intérieur (Inner Monologue)
        thought_title = QLabel("🧠 Monologue Intérieur")
        thought_title.setObjectName("SectionTitle")
        scroll_layout.addWidget(thought_title)
        
        toggle_thought_btn = QPushButton("👁️ Voir la dernière pensée")
        toggle_thought_btn.setStyleSheet("QPushButton { background: #3a3d41; color: #d4d4d4; border: 1px solid #4a4a4a; padding: 6px; border-radius: 4px; } QPushButton:hover { background: #45494e; }")
        
        thought_container = QWidget()
        thought_layout = QVBoxLayout(thought_container)
        thought_layout.setContentsMargins(0, 5, 0, 10)
        
        display_thought = last_thought if last_thought else "Aucune réflexion récente détectée."
        if len(display_thought) > 400:
            display_thought = display_thought[:400] + "...\n\n[Texte tronqué]"
            
        escaped_thought = html.escape(display_thought).replace(chr(10), '<br>')
        thought_lbl = QLabel(f"<div style='background: rgba(255,255,255,0.05); border-left: 3px solid #c586c0; padding: 10px; color: #c586c0; font-style: italic;'>{escaped_thought}</div>")
        thought_lbl.setWordWrap(True)
        thought_layout.addWidget(thought_lbl)
        thought_container.hide()
        
        def toggle_thought(*args):
            if thought_container.isHidden():
                thought_container.show()
                toggle_thought_btn.setText("🙈 Cacher la dernière pensée")
            else:
                thought_container.hide()
                toggle_thought_btn.setText("👁️ Voir la dernière pensée")
                
        toggle_thought_btn.clicked.connect(toggle_thought)
        
        scroll_layout.addWidget(toggle_thought_btn)
        scroll_layout.addWidget(thought_container)
            
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Override Input (Chat direct)
        override_layout = QHBoxLayout()
        override_input = QLineEdit()
        override_input.setPlaceholderText(f"Envoyer une directive directe à {agent_id}...")
        override_input.setStyleSheet("QLineEdit { background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 4px; color: #d4d4d4; padding: 6px; }")
        
        override_btn = QPushButton("Envoyer")
        override_btn.setStyleSheet("QPushButton { background: #007acc; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; } QPushButton:hover { background: #0098ff; }")
        
        def send_override():
            text = override_input.text().strip()
            if not text: return
            if not (hasattr(self, 'live_worker') and self.live_worker): return
            
            msg = {"role": "user", "content": f"[DIRECTIVE EXPLICITE DE L'UTILISATEUR]\n{text}"}
            if hasattr(self.live_worker, 'agent_histories'):
                self.live_worker.agent_histories.setdefault(agent_id, []).append(msg)
            if hasattr(self.live_worker, 'full_agent_histories'):
                self.live_worker.full_agent_histories.setdefault(agent_id, []).append(msg)
                
            self.add_system_message(f"✉️ <b>Directive envoyée manuellement à {agent_id}</b> : {html.escape(text)}")
            override_input.clear()
            
            # Optionally, we can refresh the view or flash the input to show it worked
            override_input.setPlaceholderText("Envoyé !")
            QTimer.singleShot(1500, lambda: override_input.setPlaceholderText(f"Envoyer une directive directe à {agent_id}..."))
            
        override_btn.clicked.connect(send_override)
        override_input.returnPressed.connect(send_override)
        
        override_layout.addWidget(override_input)
        override_layout.addWidget(override_btn)
        layout.addLayout(override_layout)

        
        overlay.resize(450, 550)
        
        graph_rect = self.node_graph.rect()
        overlay_x = max(10, graph_rect.width() - 470)
        overlay_y = max(10, (graph_rect.height() - 550) // 2)
        
        overlay.move(overlay_x, overlay_y)
        overlay.show()
        
        self._agent_overlay = overlay

    def show_edge_details(self, edge, pos):
        if not edge.messages:
            return
            
        if not hasattr(self, '_edge_overlay') or not self._edge_overlay:
            self._edge_overlay = QFrame(self.node_graph)
            self._edge_overlay.setObjectName("EdgeOverlay")
            self._edge_overlay.setStyleSheet("""
                QFrame#EdgeOverlay {
                    background-color: rgba(30, 30, 35, 240);
                    border: 1px solid #c586c0;
                    border-radius: 6px;
                }
            """)
            layout = QVBoxLayout(self._edge_overlay)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(6)
            
            self._edge_title = QLabel()
            self._edge_title.setStyleSheet("font-weight: bold; color: #c586c0; font-size: 13px;")
            layout.addWidget(self._edge_title)
            
            self._edge_list = QLabel()
            self._edge_list.setStyleSheet("color: #d4d4d4;")
            self._edge_list.setWordWrap(True)
            layout.addWidget(self._edge_list)
            
        source_name = AGENTS_CONFIG.get(edge.source_node.node_id, {}).get("name", edge.source_node.node_id) if hasattr(edge, 'source_node') else "Source"
        dest_name = AGENTS_CONFIG.get(edge.dest_node.node_id, {}).get("name", edge.dest_node.node_id) if hasattr(edge, 'dest_node') else "Dest"
        
        self._edge_title.setText(f"Échanges : {source_name} ↔ {dest_name}")
        
        html_list = "<ul style='margin-top: 4px; padding-left: 20px; margin-bottom: 4px;'>"
        for msg in edge.messages[-5:]:
            html_list += f"<li style='padding-bottom: 2px;'>{html.escape(msg)}</li>"
        html_list += "</ul>"
        
        if len(edge.messages) > 5:
            html_list += f"<div style='color: #888; font-size: 11px; font-style: italic; text-align: right;'>+ {len(edge.messages)-5} autres messages...</div>"
            
        self._edge_list.setText(html_list)
        self._edge_overlay.adjustSize()
        
        target_x = int(pos.x()) + 15
        target_y = int(pos.y()) + 15
        
        graph_rect = self.node_graph.rect()
        if target_x + self._edge_overlay.width() > graph_rect.width():
            target_x = int(pos.x()) - self._edge_overlay.width() - 15
            
        if target_y + self._edge_overlay.height() > graph_rect.height():
            target_y = int(pos.y()) - self._edge_overlay.height() - 15
            
        self._edge_overlay.move(max(0, target_x), max(0, target_y))
        self._edge_overlay.show()

    def hide_edge_details(self, edge):
        if hasattr(self, '_edge_overlay') and self._edge_overlay:
            self._edge_overlay.hide()

    def go_back(self):
        self.wants_to_go_back = True
        self.close()

class WhipAnimationWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(parent.size())
        self.progress = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_anim)
        self.timer.start(16)
        self.elapsed = 0
        self.duration = 900
        
    def update_anim(self):
        self.elapsed += 16
        self.progress = min(1.0, self.elapsed / self.duration)
        self.update()
        if self.progress >= 1.0:
            self.timer.stop()
            self.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        path = QPainterPath()
        
        hx = w * 0.1
        hy = h * 0.8
        
        path.moveTo(hx, hy)
        
        crack_x, crack_y = w * 0.8, h * 0.4
        
        if self.progress < 0.4:
            p = self.progress / 0.4
            tx = hx - w * 0.1 * p
            ty = hy - h * 0.6 * p
            
            cx1 = hx + w * 0.2 * p
            cy1 = hy - h * 0.2 * p
            
            cx2 = tx + w * 0.2 * p
            cy2 = ty - h * 0.1 * p
            
            path.cubicTo(cx1, cy1, cx2, cy2, tx, ty)
            
        elif self.progress < 0.6:
            p = (self.progress - 0.4) / 0.2
            p_ease = math.sin(p * math.pi / 2)
            
            loop_x = hx + (crack_x - hx) * p_ease
            loop_y = hy + (crack_y - hy) * p_ease - h * 0.2 * math.sin(p_ease * math.pi)
            
            cx1 = hx + (loop_x - hx) * 0.3
            cy1 = hy + (loop_y - hy) * 0.3 + 50
            
            cx2 = loop_x - 50
            cy2 = loop_y - 100
            
            path.cubicTo(cx1, cy1, cx2, cy2, loop_x, loop_y)
            
            if p_ease < 0.9:
                trail_p = (1.0 - p_ease)
                tip_x = loop_x - w * 0.15 * trail_p
                tip_y = loop_y - h * 0.3 * trail_p
                path.quadTo(loop_x + 30 * trail_p, loop_y + 50 * trail_p, tip_x, tip_y)
            else:
                path.lineTo(crack_x, crack_y)
            
            if p > 0.5:
                flash_p = (p - 0.5) / 0.5
                self.draw_explosion(painter, crack_x, crack_y, flash_p)
                
        else:
            p = (self.progress - 0.6) / 0.4
            
            if p < 0.5:
                flash_p = 1.0 - (p / 0.5)
                self.draw_explosion(painter, crack_x, crack_y, flash_p)
            
            recoil_p = 1.0 - (1.0 - p)**2
            
            tx = crack_x - (crack_x - hx) * recoil_p
            ty = crack_y - (crack_y - hy) * recoil_p + h * 0.4 * math.sin(recoil_p * math.pi)
            
            cx1 = hx + (tx - hx) * 0.3
            cy1 = hy + (ty - hy) * 0.3 + 150 * math.sin(recoil_p * math.pi)
            
            cx2 = hx + (tx - hx) * 0.7
            cy2 = hy + (ty - hy) * 0.7 + 100 * math.sin(recoil_p * math.pi)
            
            path.cubicTo(cx1, cy1, cx2, cy2, tx, ty)

        alpha = 255 if self.progress < 0.8 else int(255 * (1.0 - (self.progress - 0.8) / 0.2))
        pen = QPen(QColor(139, 69, 19, alpha), 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)
        
        painter.setPen(QPen(QColor(80, 40, 10, alpha), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(int(hx), int(hy), int(hx - 20), int(hy + 40))
        
        painter.end()

    def draw_explosion(self, painter, crack_x, crack_y, flash_p):
        painter.setPen(QPen(QColor(255, 200, 50, int(255 * (1 - flash_p))), 4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        ring_r = 20 + flash_p * 80
        painter.drawEllipse(int(crack_x - ring_r), int(crack_y - ring_r), int(ring_r * 2), int(ring_r * 2))
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, int(255 * (1 - flash_p))))
        core_r = 15 + flash_p * 15
        painter.drawEllipse(int(crack_x - core_r), int(crack_y - core_r), int(core_r * 2), int(core_r * 2))
        
        painter.setPen(QPen(QColor(255, 100, 0, int(255 * (1 - flash_p))), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(8):
            angle = i * math.pi / 4 + flash_p * 0.5
            r1 = 15 + flash_p * 30
            r2 = 40 + flash_p * 80
            painter.drawLine(
                int(crack_x + math.cos(angle)*r1), int(crack_y + math.sin(angle)*r1),
                int(crack_x + math.cos(angle)*r2), int(crack_y + math.sin(angle)*r2)
            )
        
        painter.setPen(QColor(255, 50, 50, int(255 * (1 - flash_p))))
        font = painter.font()
        font.setPixelSize(int(40 + flash_p * 60))
        font.setBold(True)
        font.setItalic(True)
        painter.setFont(font)
        text_rect = painter.boundingRect(int(crack_x) - 200, int(crack_y) - 150, 400, 100, Qt.AlignmentFlag.AlignCenter, "TCHACK !")
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "TCHACK !")

class DynamicThinkingAnimationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(70, 32)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.phase = 0.0
        self.agent_id = "orchestrator"
        
    def set_agent(self, agent_id):
        self.agent_id = agent_id
        
    def start_anim(self):
        self.show()
        self.timer.start(40)
        
    def stop_anim(self):
        self.timer.stop()
        self.hide()
        
    def advance(self):
        self.phase += 0.2
        if self.phase > math.pi * 2:
            self.phase -= math.pi * 2
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        cx = self.width() / 2
        cy = self.height() / 2
        
        if self.agent_id == "coder":
            # Pac-Man (Codeur)
            mcx = 15
            mouth = abs(math.sin(self.phase * 2)) * 40
            painter.setBrush(QColor(255, 215, 0)) # Jaune
            painter.setPen(Qt.PenStyle.NoPen)
            start_angle = int(mouth * 16)
            span_angle = int((360 - mouth * 2) * 16)
            painter.drawPie(int(mcx - 10), int(cy - 10), 20, 20, start_angle, span_angle)
            painter.setBrush(QColor(200, 200, 200))
            dot_offset = (self.phase * 15) % 20
            for i in range(3):
                dx = mcx + 15 + i * 20 - dot_offset
                if dx > mcx + 5:
                    painter.drawEllipse(int(dx - 2), int(cy - 2), 4, 4)

        elif self.agent_id == "orchestrator":
            # Réseau de neurones / Chef d'orchestre
            painter.setBrush(QColor(14, 99, 156))
            painter.setPen(QPen(QColor(14, 99, 156), 2))
            for i in range(3):
                angle = self.phase + i * (math.pi * 2 / 3)
                x = cx + math.cos(angle) * 12
                y = cy + math.sin(angle) * 6
                painter.drawLine(int(cx), int(cy), int(x), int(y))
                painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)
            painter.setBrush(QColor(197, 134, 192))
            pulse = abs(math.sin(self.phase * 2)) * 3
            painter.drawEllipse(int(cx - 5 - pulse), int(cy - 5 - pulse), int(10 + pulse * 2), int(10 + pulse * 2))

        elif self.agent_id == "reviewer":
            # Loupe de recherche (Relecteur)
            scan_x = math.sin(self.phase) * 15
            painter.setPen(QPen(QColor(150, 150, 150), 2))
            painter.drawLine(int(cx + scan_x + 5), int(cy + 5), int(cx + scan_x + 10), int(cy + 10))
            painter.setBrush(QColor(0, 150, 255, 80))
            painter.setPen(QPen(QColor(150, 150, 150), 2))
            painter.drawEllipse(int(cx + scan_x - 5), int(cy - 5), 10, 10)

        elif self.agent_id == "architect":
            # Briques de construction (Architecte)
            painter.setBrush(QColor(200, 100, 50))
            painter.setPen(QPen(QColor(50, 50, 50), 1))
            bw, bh = 10, 6
            progress = (self.phase / (math.pi * 2)) * 6
            drawn = 0
            for row in range(3):
                for col in range(3 - row):
                    if drawn < progress:
                        x = cx - (3 - row) * bw / 2 + col * bw
                        y = cy + 10 - row * bh
                        painter.drawRect(int(x), int(y - bh), bw, bh)
                    drawn += 1

        elif self.agent_id == "tester":
            # Radar de bugs (Testeur)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(89, 209, 133), 2))
            pulse = (math.sin(self.phase * 4) + 1) / 2
            radius = 12 * pulse
            painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))
            painter.setBrush(QColor(89, 209, 133))
            painter.drawEllipse(int(cx - 2), int(cy - 2), 4, 4)

        else:
            # Défaut : Onde sonore (Autres agents locaux)
            for i in range(5):
                painter.setBrush(QColor(14, 99, 156))
                painter.setPen(Qt.PenStyle.NoPen)
                offset = i * 0.5
                h = abs(math.sin(self.phase * 2 + offset)) * 12 + 2
                x = cx - 15 + i * 8
                painter.drawRect(int(x - 2), int(cy - h / 2), 4, int(h))

class EyeThinkingAnimationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 32)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.phase = 0.0

    def start_anim(self):
        self.show()
        self.timer.start(50)

    def stop_anim(self):
        self.timer.stop()
        self.hide()

    def advance(self):
        self.phase += 0.15
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        cx = self.width() / 2
        cy = self.height() / 2
        
        path = QPainterPath()
        path.moveTo(cx - 20, cy)
        path.quadTo(cx, cy - 15, cx + 20, cy)
        path.quadTo(cx, cy + 15, cx - 20, cy)
        
        painter.setBrush(QColor(40, 40, 40))
        painter.setPen(QPen(QColor(197, 134, 192), 2)) # Contour violet/rose (Thème IA)
        painter.drawPath(path)
        
        blink = abs(math.sin(self.phase * 0.5))
        if blink < 0.15:
            # L'œil se ferme (clignement)
            painter.setBrush(QColor(197, 134, 192))
            painter.drawLine(int(cx - 20), int(cy), int(cx + 20), int(cy))
            return
            
        # Mouvement de la pupille
        look_x = math.sin(self.phase * 0.8) * 7
        
        # Iris
        painter.setBrush(QColor(197, 134, 192))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(cx + look_x - 6), int(cy - 6), 12, 12)
        
        # Pupille
        painter.setBrush(QColor(0, 0, 0))
        painter.drawEllipse(int(cx + look_x - 3), int(cy - 3), 6, 6)

class RealisticProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(12)
        
        self.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                background-color: #2d2d30;
                margin-top: 4px;
                margin-bottom: 4px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0e639c, stop:1 #1177bb);
                border-radius: 5px;
            }
        """)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.progress_value = 0.0
        
    def start_anim(self):
        self.progress_value = 0.0
        self.setValue(0)
        self.show()
        self.timer.start(100)
        
    def advance(self):
        remaining = 95.0 - self.progress_value
        if remaining > 0.5:
            step = max(0.5, remaining * 0.05)
            self.progress_value += step
            self.setValue(int(self.progress_value))
            
    def stop_anim(self):
        self.timer.stop()
        self.setValue(100)
        QTimer.singleShot(400, self.hide_and_reset)
        
    def hide_and_reset(self):
        self.hide()
        self.setValue(0)
