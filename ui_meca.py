import logging
import subprocess
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QPushButton, QMessageBox

logger = logging.getLogger(__name__)

class MecaPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        self.meca_tab = QWidget()
        meca_layout = QVBoxLayout(self.meca_tab)
        meca_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- Toolbar Meca ---
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        toolbar_layout.addWidget(QLabel("🛠️ Outils CAO 3D :"))
        
        self.btn_view = QPushButton("👁️ Voir dans CQ-Editor")
        self.btn_view.clicked.connect(self.open_in_cq_editor)
        
        toolbar_layout.addWidget(self.btn_view)
        
        meca_layout.addLayout(toolbar_layout)
        
        # --- Chat UI (reuse main_window logic) ---
        meca_layout.addWidget(self.main_window._build_chat_panel())
        
        self.tabs.addTab(self.meca_tab, "Agent Concepteur 3D")
        
        self.layout.addWidget(self.tabs)

    def open_in_cq_editor(self):
        from PyQt6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un fichier à ouvrir dans CQ-Editor",
            "",
            "Fichiers CadQuery / STEP (*.py *.step);;Tous les fichiers (*.*)"
        )
        
        if not file_path:
            return
            
        try:
            self.main_window.add_system_message(f"Tentative d'ouverture de '{os.path.basename(file_path)}' dans CQ-Editor...")
            
            if file_path.lower().endswith('.step') or file_path.lower().endswith('.stp'):
                # Script autogénéré pour visualiser le STEP dans CQ-Editor
                script_name = "temp_viewer.py"
                script_content = f"""import cadquery as cq

# Script autogénéré pour visualiser le STEP dans CQ-Editor
shape = cq.importers.importStep(r'{file_path}')
if 'show_object' in locals():
    show_object(shape)
"""
                with open(script_name, "w", encoding="utf-8") as file:
                    file.write(script_content)
                from core.sandbox import resolve_external_binary, hardened_subprocess_env
                cq_bin = resolve_external_binary("cq-editor")
                if not cq_bin:
                    raise FileNotFoundError("L'exécutable cq-editor est introuvable dans le PATH.")
                
                subprocess.Popen([cq_bin, script_name], env=hardened_subprocess_env())
            else:
                from core.sandbox import resolve_external_binary, hardened_subprocess_env
                cq_bin = resolve_external_binary("cq-editor")
                if not cq_bin:
                    raise FileNotFoundError("L'exécutable cq-editor est introuvable dans le PATH.")
                    
                subprocess.Popen([cq_bin, file_path], env=hardened_subprocess_env())
                
        except FileNotFoundError:
            QMessageBox.critical(
                self, "Erreur",
                "La commande 'cq-editor' est introuvable. "
                "Assurez-vous que l'application est installée et accessible dans votre PATH."
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir CQ-Editor : {e}")
