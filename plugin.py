import logging
import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt

logger = logging.getLogger("QgisAgent")


class QgisAgentPlugin:
    """QGIS Agent - AI-powered GIS assistant sidebar plugin."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.sidebar = None
        self._llm = None

    def initGui(self):
        try:
            from .llm_client import LLMClient
            self._llm = LLMClient()

            icon_path = os.path.join(self.plugin_dir, "icon.png")
            self.action = QAction(
                QIcon(icon_path),
                "QGIS Agent",
                self.iface.mainWindow(),
            )
            self.action.setObjectName("qgisAgentAction")
            self.action.setToolTip("Open QGIS Agent sidebar")
            self.action.setCheckable(True)
            self.action.triggered.connect(self._toggle_sidebar)

            self.iface.addToolBarIcon(self.action)
            self.iface.addPluginToMenu("&QGIS Agent", self.action)

            self._create_sidebar()
        except Exception as e:
            logger.exception("Failed to initialize QGIS Agent plugin")

    def unload(self):
        try:
            if self.action:
                self.iface.removeToolBarIcon(self.action)
                self.iface.removePluginMenu("&QGIS Agent", self.action)

            if self.sidebar is not None:
                self.iface.mainWindow().removeDockWidget(self.sidebar)
                self.sidebar = None
        except Exception as e:
            logger.exception("Failed to unload QGIS Agent plugin")

    def _create_sidebar(self):
        from .sidebar import SidebarWidget
        self.sidebar = SidebarWidget(self.iface, self._llm, self.iface.mainWindow())
        self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, self.sidebar)
        self.sidebar.setVisible(True)
        self.action.setChecked(True)

    def _toggle_sidebar(self, checked):
        if self.sidebar is None:
            return
        self.sidebar.setVisible(checked)
