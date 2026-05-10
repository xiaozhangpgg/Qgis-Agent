import logging
import os
import traceback

from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.core import Qgis, QgsMessageLog

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
            from .core.llm_client import LLMClient
            from qgis.core import QgsSettings
            self._llm = LLMClient()

            # Load saved LLM configuration from QgsSettings
            settings = QgsSettings()
            provider = settings.value("QgisAgent/provider", "")
            api_key = settings.value("QgisAgent/api_key", "")
            model = settings.value("QgisAgent/model", "")
            base_url = settings.value("QgisAgent/base_url", "")
            if provider and api_key and model:
                self._llm.configure(provider, api_key, model, base_url or None)

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

            # Log successful startup to QGIS message log
            QgsMessageLog.logMessage("QGIS Agent 插件加载成功", "QgisAgent", Qgis.MessageLevel.Info)
        except Exception as e:
            error_msg = f"QGIS Agent 插件初始化失败:\n{str(e)}\n\n{traceback.format_exc()}"
            logger.exception("Failed to initialize QGIS Agent plugin")
            QgsMessageLog.logMessage(error_msg, "QgisAgent", Qgis.MessageLevel.Critical)
            self.iface.messageBar().pushMessage(
                "QGIS Agent", f"插件初始化失败: {str(e)}", level=Qgis.MessageLevel.Critical, duration=10
            )

    def unload(self):
        try:
            if self.action:
                self.iface.removeToolBarIcon(self.action)
                self.iface.removePluginMenu("&QGIS Agent", self.action)

            if self.sidebar is not None:
                self.iface.mainWindow().removeDockWidget(self.sidebar)
                self.sidebar.deleteLater()
                self.sidebar = None
        except Exception as e:
            logger.exception("Failed to unload QGIS Agent plugin")

    def _create_sidebar(self):
        from .ui.sidebar import SidebarWidget
        self.sidebar = SidebarWidget(self.iface, self._llm, self.iface.mainWindow())
        self.iface.mainWindow().addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.sidebar)
        self.sidebar.show()
        self.sidebar.raise_()
        self.action.setChecked(True)

    def _toggle_sidebar(self, checked):
        if self.sidebar is None:
            return
        self.sidebar.setVisible(checked)
        if checked:
            self.sidebar.show()
            self.sidebar.raise_()
