import logging
import os

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsMessageLog


class QgsMessageLogHandler(logging.Handler):
    """Python logging handler that outputs to QGIS Message Log."""

    def emit(self, record):
        msg = self.format(record)
        # QGIS message levels: 0=INFO, 1=WARNING, 2=CRITICAL
        level_map = {
            logging.DEBUG: 0,
            logging.INFO: 0,
            logging.WARNING: 1,
            logging.ERROR: 2,
            logging.CRITICAL: 2,
        }
        QgsMessageLog.logMessage(msg, "QgisAgent", level_map.get(record.levelno, 0))


# Configure QGIS Agent logger
logger = logging.getLogger("QgisAgent")
logger.setLevel(logging.DEBUG)
handler = QgsMessageLogHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)


def classFactory(iface):
    from .plugin import QgisAgentPlugin
    return QgisAgentPlugin(iface)
