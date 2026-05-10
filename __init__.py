import logging
import os

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsMessageLog


class QgsMessageLogHandler(logging.Handler):
    """Python logging handler that outputs to QGIS Message Log."""

    def emit(self, record):
        msg = self.format(record)
        # QGIS message levels: Qgis.Info=0, Qgis.Warning=1, Qgis.Critical=2
        from qgis.core import Qgis
        level_map = {
            logging.DEBUG: Qgis.Info,
            logging.INFO: Qgis.Info,
            logging.WARNING: Qgis.Warning,
            logging.ERROR: Qgis.Critical,
            logging.CRITICAL: Qgis.Critical,
        }
        QgsMessageLog.logMessage(msg, "QgisAgent", level_map.get(record.levelno, Qgis.Info))


# Configure QGIS Agent logger
logger = logging.getLogger("QgisAgent")
logger.setLevel(logging.DEBUG)
handler = QgsMessageLogHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)


def classFactory(iface):
    from .plugin import QgisAgentPlugin
    return QgisAgentPlugin(iface)
