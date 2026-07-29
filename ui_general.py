import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

logger = logging.getLogger(__name__)

class GeneralPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        self.tabs.addTab(self.main_window._build_generalist_panel(), "Assistant Général")
        
        self.layout.addWidget(self.tabs)
