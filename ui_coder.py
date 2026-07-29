import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

logger = logging.getLogger(__name__)

class CoderPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        # We delegate the actual creation of these complex tabs back to the main window
        # to preserve all the tight signal/slot couplings and object references 
        # (like self.chat_display, self.agent_combo, etc.) that the main window expects to own.
        self.tabs.addTab(self.main_window._build_chat_panel(), "Agent Codeur")
        
        self.layout.addWidget(self.tabs)

