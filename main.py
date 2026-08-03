# ==========================================
# VERSIONING DU CODE
# Voir CHANGELOG.md pour l'historique des versions.
# ==========================================

import sys
import logging
try:
    import onnxruntime
except ImportError:
    pass

from PyQt6.QtWidgets import QApplication, QDialog

from ui import DARK_QSS, ConnectionDialog, MainWindow

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("[LOG - SYSTEM] Lancement de 'L'Atelier IA V4.4.1'")
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)

    while True:
        dialog = ConnectionDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_auth_mode, selected_app_mode, is_demo = dialog.get_selection()
            
            # Load appropriate config
            from core.utils import load_agents_config
            load_agents_config(selected_app_mode)
            
            window = MainWindow(auth_mode=selected_auth_mode, app_mode=selected_app_mode, is_demo=is_demo)
            window.show()
            app.exec()
            
            # Si l'utilisateur a cliqué sur "Retour" pour changer de mode de connexion
            if hasattr(window, 'wants_to_go_back') and window.wants_to_go_back:
                continue
            else:
                break
        else:
            break

    sys.exit(0)
