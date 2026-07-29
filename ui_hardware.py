import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QPushButton, QMessageBox, QDialog, QScrollArea, QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)

class HardwarePanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        self.skidl_tab = QWidget()
        skidl_layout = QVBoxLayout(self.skidl_tab)
        skidl_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- Toolbar SKIDL ---
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        toolbar_layout.addWidget(QLabel("🛠️ Outils SKIDL :"))
        
        self.btn_netlist = QPushButton("🖨️ Générer la Netlist")
        self.btn_netlist.clicked.connect(self.generate_netlist)
        
        self.btn_erc = QPushButton("🔍 Vérifier l'ERC")
        self.btn_erc.clicked.connect(self.verify_erc)
        
        self.btn_components = QPushButton("🔌 Voir les composants")
        self.btn_components.clicked.connect(self.view_components)
        
        self.btn_pcbparts = QPushButton("🔍 Recherche PCBParts")
        self.btn_pcbparts.clicked.connect(self.search_pcbparts)
        
        toolbar_layout.addWidget(self.btn_netlist)
        toolbar_layout.addWidget(self.btn_erc)
        toolbar_layout.addWidget(self.btn_components)
        toolbar_layout.addWidget(self.btn_pcbparts)
        
        skidl_layout.addLayout(toolbar_layout)
        
        # --- Chat UI (reuse main_window logic) ---
        skidl_layout.addWidget(self.main_window._build_chat_panel())
        
        self.tabs.addTab(self.skidl_tab, "Agent Concepteur (SKIDL)")
        
        self.layout.addWidget(self.tabs)
        
        # Demander les chemins KiCad au démarrage si manquant
        self._check_kicad_env()

    def _check_kicad_env(self):
        import os
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        
        env_vars = ["KICAD_SYMBOL_DIR", "KICAD9_SYMBOL_DIR", "KICAD8_SYMBOL_DIR", "KICAD7_SYMBOL_DIR", "KICAD6_SYMBOL_DIR"]
        if any(var in os.environ for var in env_vars):
            return
            
        reply = QMessageBox.question(
            self, "Configuration KiCad",
            "Les variables d'environnement KiCad ne sont pas définies sur ce système.\n"
            "Souhaitez-vous configurer le chemin d'accès aux librairies KiCad pour cette session ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            default_sym_path = r"C:\Program Files\KiCad\9.0\share\kicad\symbols"
            sym_path, ok1 = QInputDialog.getText(
                self, "Chemin des symboles KiCad",
                "Chemin vers le dossier 'symbols' (ex: C:\\Program Files\\KiCad\\9.0\\share\\kicad\\symbols) :",
                text=default_sym_path
            )
            if ok1 and sym_path:
                for var in env_vars:
                    os.environ[var] = sym_path
                
                # S'assurer que le main_window a la méthode avant d'appeler
                if hasattr(self.main_window, 'add_system_message'):
                    self.main_window.add_system_message(f"✅ <b>Symboles KiCad définis temporairement</b> vers : {sym_path}")

            default_fp_path = r"C:\Program Files\KiCad\9.0\share\kicad\footprints"
            fp_path, ok2 = QInputDialog.getText(
                self, "Chemin des empreintes KiCad",
                "Chemin vers le dossier 'footprints' (ex: C:\\Program Files\\KiCad\\9.0\\share\\kicad\\footprints) :",
                text=default_fp_path
            )
            if ok2 and fp_path:
                os.environ["KICAD9_FOOTPRINT_DIR"] = fp_path
                if hasattr(self.main_window, 'add_system_message'):
                    self.main_window.add_system_message(f"✅ <b>Empreintes KiCad définies temporairement</b> vers : {fp_path}")

    # ------------------------------------------------------------------ #
    #  Exécution en arrière-plan (V4.4.0)                                 #
    # ------------------------------------------------------------------ #
    # ROBUSTESSE : run_python_script (jusqu'à 60 s) et la recherche
    # PCBParts (30 s) tournaient sur le thread PRINCIPAL -> interface
    # figée pendant toute la durée de l'appel. Ces opérations passent
    # désormais par un FunctionWorker (core.workers). Le worker est stocké
    # sur main_window._task_worker pour être annulé/attendu par closeEvent.
    def _run_in_background(self, fn, on_done, *args, **kwargs):
        from core.workers import FunctionWorker
        existing = getattr(self.main_window, '_task_worker', None)
        if existing and existing.isRunning():
            QMessageBox.information(self, "Occupé",
                                    "Une opération est déjà en cours, patientez.")
            return False
        worker = FunctionWorker(fn, *args, **kwargs)
        worker.finished_task.connect(on_done)
        self.main_window._task_worker = worker
        worker.start()
        return True

    def _set_toolbar_enabled(self, enabled):
        for btn in (self.btn_netlist, self.btn_erc, self.btn_components, self.btn_pcbparts):
            btn.setEnabled(enabled)

    def _run_current_skidl_script(self, action_name):
        current_file = self.main_window.current_file
        if not current_file:
            QMessageBox.warning(self, "Erreur", "Veuillez ouvrir un script SKIDL dans l'éditeur.")
            return
            
        if not self.main_window.sandbox:
            QMessageBox.warning(self, "Erreur", "Aucun projet ouvert.")
            return

        # SÉCURITÉ (V4.4.0) : ce bouton EXÉCUTE un script du projet — script
        # que l'agent Codeur a potentiellement écrit. C'est la même classe de
        # risque qui a motivé le retrait de pytest de la liste blanche. On
        # avertit explicitement l'utilisateur, comme pour graphify.
        import os
        reply = QMessageBox.question(
            self, f"{action_name} — Confirmation",
            f"Cette action va EXÉCUTER le script Python suivant sur votre machine,\n"
            f"avec vos droits utilisateur :\n\n{os.path.basename(current_file)}\n\n"
            f"⚠️ Si ce script a été écrit ou modifié par un agent, relisez-le avant\n"
            f"d'autoriser (il sera exécuté tel quel).\n\nContinuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.main_window.add_system_message(f"⏳ <b>{action_name}</b> en cours d'exécution...")
        self._set_toolbar_enabled(False)

        def on_done(success, result):
            self._set_toolbar_enabled(True)
            if not success:
                self.main_window.add_system_message(f"❌ <b>Erreur {action_name} :</b> {result}")
                QMessageBox.warning(self, "Erreur", str(result))
                return
            formatted_result = str(result).replace('\n', '<br>')
            self.main_window.add_system_message(f"<b>Résultat {action_name} :</b><br><pre>{formatted_result}</pre>")
            if "SUCCÈS" in str(result).split("\n", 1)[0]:
                QMessageBox.information(self, "Succès", f"{action_name} terminée avec succès.")
            else:
                QMessageBox.warning(self, "Erreur", f"{action_name} a rencontré un problème. Vérifiez les messages système.")

        self._run_in_background(self.main_window.sandbox.run_python_script,
                                on_done, current_file)

    def generate_netlist(self):
        self._run_current_skidl_script("Génération de Netlist")
        
    def verify_erc(self):
        self._run_current_skidl_script("Vérification ERC")
        
    def view_components(self):
        from PyQt6.QtWidgets import QInputDialog
        
        if not self.main_window.sandbox:
            QMessageBox.warning(self, "Erreur", "Aucun projet ouvert.")
            return
            
        term, ok = QInputDialog.getText(self, "Recherche de Composants", "Entrez un mot-clé (ex: resistor, R, capacitor) :")
        if ok and term:
            self.main_window.add_system_message(f"⏳ <b>Recherche SKIDL :</b> '{term}'...")
            self._set_toolbar_enabled(False)
            
            temp_script = ".skidl_search_tmp.py"
            # BUGFIX CRITIQUE (V4.4.0) : l'ancienne f-string utilisait '\\n'
            # (antislash + n LITTÉRAL) -> le script généré tenait sur une
            # seule ligne et levait SyntaxError à CHAQUE exécution. On écrit
            # de vrais sauts de ligne, et le terme passe par repr() ({term!r})
            # pour neutraliser apostrophes et caractères spéciaux (l'ancien
            # code cassait sur un terme contenant « ' » — injection de code).
            code = f"from skidl import search\nsearch({term!r})\n"

            def run_search():
                sandbox = self.main_window.sandbox
                sandbox.write_file(temp_script, code)
                try:
                    return sandbox.run_python_script(temp_script)
                finally:
                    try:
                        sandbox.delete_file(temp_script)
                    except Exception:
                        pass

            def on_done(success, result):
                self._set_toolbar_enabled(True)
                if not success:
                    QMessageBox.warning(self, "Erreur", f"Erreur lors de la recherche : {result}")
                    return
                formatted_result = str(result).replace('\n', '<br>')
                self.main_window.add_system_message(f"<b>Résultat Recherche :</b><br><pre>{formatted_result}</pre>")

            self._run_in_background(run_search, on_done)

    def search_pcbparts(self):
        from PyQt6.QtWidgets import QInputDialog
        
        if not self.main_window.sandbox:
            QMessageBox.warning(self, "Erreur", "Aucun projet ouvert.")
            return
            
        term, ok = QInputDialog.getText(self, "Recherche PCBParts", "Entrez la référence d'un composant (ex: LM358, ESP32) :")
        if ok and term:
            self.main_window.add_system_message(f"⏳ <b>Recherche PCBParts :</b> '{term}'...")
            self._set_toolbar_enabled(False)

            def on_done(success, result):
                self._set_toolbar_enabled(True)
                if not success:
                    self.main_window.add_system_message(f"❌ <b>Erreur PCBParts :</b> {result}")
                    QMessageBox.warning(self, "Erreur", str(result))
                    return
                ok_flag, result_data = result
                if ok_flag:
                    self.main_window.add_system_message("✅ <b>Recherche PCBParts terminée.</b> Affichage des résultats.")
                    dialog = PcbPartsResultDialog(self, term, result_data)
                    dialog.exec()
                else:
                    self.main_window.add_system_message(f"❌ <b>Erreur PCBParts :</b> {result_data}")
                    QMessageBox.warning(self, "Erreur", str(result_data))

            self._run_in_background(self.main_window.sandbox.search_mcp_pcbparts,
                                    on_done, term)

class PcbPartsResultDialog(QDialog):
    def __init__(self, parent, term, results):
        super().__init__(parent)
        self.setWindowTitle(f"Résultats PCBParts pour '{term}'")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        container = QWidget()
        container_layout = QVBoxLayout(container)

        # SÉCURITÉ (V4.4.0) : les chaînes viennent d'un serveur DISTANT
        # (pcbparts.dev). QLabel interprète le rich text par défaut — une
        # réponse contenant du HTML pouvait truquer l'affichage. Tous les
        # labels de données sont désormais en texte brut.
        def _plain(text):
            lbl = QLabel(str(text))
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            return lbl
        
        for r in results:
            group = QGroupBox(f"{r.get('model', 'N/A')} ({r.get('manufacturer', 'N/A')})")
            g_layout = QFormLayout(group)
            
            g_layout.addRow("Fournisseur :", _plain("JLCPCB"))
            g_layout.addRow("LCSC :", _plain(r.get('lcsc', 'N/A')))
            g_layout.addRow("Package :", _plain(r.get('package', 'N/A')))
            g_layout.addRow("Prix :", _plain(f"${r.get('price', 'N/A')}"))
            g_layout.addRow("Stock :", _plain(r.get('stock', 'N/A')))
            
            desc_label = _plain(r.get('description', 'N/A'))
            desc_label.setWordWrap(True)
            g_layout.addRow("Description :", desc_label)
            
            specs = r.get('specs', {})
            if specs:
                table = QTableWidget(len(specs), 2)
                table.setHorizontalHeaderLabels(["Spécification", "Valeur"])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                table.verticalHeader().setVisible(False)
                
                row = 0
                for k, v in specs.items():
                    table.setItem(row, 0, QTableWidgetItem(str(k)))
                    table.setItem(row, 1, QTableWidgetItem(str(v)))
                    row += 1
                
                # Hauteur dynamique pour ne pas trop prendre de place
                table.setFixedHeight(min(250, 35 + 30 * len(specs)))
                g_layout.addRow("Spécifications :", table)
                
            container_layout.addWidget(group)
            
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
