import json

from qgis.PyQt.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QToolButton, QWidget, QApplication,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QPalette


def _palette_color(role: QPalette.ColorRole) -> QColor:
    return QApplication.palette().color(role)


def _is_dark() -> bool:
    bg = _palette_color(QPalette.ColorRole.Window)
    return bg.lightness() < 128


# Status colors
COLOR_RUNNING = "#2196F3"
COLOR_SUCCESS = "#4CAF50"
COLOR_ERROR = "#F44336"
COLOR_PENDING = "#FF9800"


class ToolCardWidget(QFrame):
    """Collapsible tool call card with status indicator."""

    def __init__(self, tool_name: str, params: dict, parent=None):
        super().__init__(parent)
        self._tool_name = tool_name
        self._params = params
        self._expanded = False
        self._status = "running"
        self._init_ui()
        self._apply_style()

    def _init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Color bar
        self._color_bar = QFrame()
        self._color_bar.setFixedWidth(3)
        main_layout.addWidget(self._color_bar)

        # Content area
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(10, 12, 10, 12)
        self._content_layout.setSpacing(4)
        main_layout.addWidget(content, 1)

        # Header row (clickable)
        self._header = QWidget()
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self._status_icon = QLabel("⟳")
        self._status_icon.setFixedWidth(16)
        header_layout.addWidget(self._status_icon)

        self._name_label = QLabel(f"<code>{self._tool_name}</code>")
        header_layout.addWidget(self._name_label)

        header_layout.addStretch()

        self._time_label = QLabel("")
        self._time_label.setStyleSheet("color: gray; font-size: 11px;")
        header_layout.addWidget(self._time_label)

        self._expand_btn = QToolButton()
        self._expand_btn.setText("▸")
        self._expand_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._expand_btn.setFixedSize(16, 16)
        header_layout.addWidget(self._expand_btn)

        self._content_layout.addWidget(self._header)

        # Detail area (collapsible)
        self._detail_widget = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_widget)
        self._detail_layout.setContentsMargins(0, 4, 0, 0)

        params_text = json.dumps(self._params, ensure_ascii=False, indent=2)
        self._params_label = QLabel(params_text)
        self._params_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._params_label.setWordWrap(True)
        base_color = _palette_color(QPalette.ColorRole.Base).name()
        self._params_label.setStyleSheet(
            f"font-family: Consolas, Monaco, monospace; font-size: 12px; "
            f"background: {base_color}; padding: 6px; border-radius: 3px;"
        )
        self._detail_layout.addWidget(self._params_label)

        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._result_label.setVisible(False)
        self._detail_layout.addWidget(self._result_label)

        self._detail_widget.setVisible(False)
        self._content_layout.addWidget(self._detail_widget)

        # Click to toggle
        self._header.mousePressEvent = lambda e: self._toggle_detail()
        self._expand_btn.clicked.connect(self._toggle_detail)

    def _apply_style(self):
        color = {
            "running": COLOR_RUNNING,
            "success": COLOR_SUCCESS,
            "error": COLOR_ERROR,
        }.get(self._status, COLOR_PENDING)

        is_dark = _is_dark()
        bg = "#2A2A2A" if is_dark else "#F8F8F8"

        self._color_bar.setStyleSheet(f"background: {color};")
        self.setStyleSheet(
            f"ToolCardWidget {{ background: {bg}; border-radius: 4px; }}"
        )

    def _toggle_detail(self):
        self._expanded = not self._expanded
        self._detail_widget.setVisible(self._expanded)
        self._expand_btn.setText("▾" if self._expanded else "▸")

    def set_result(self, success: bool, result: str, elapsed: float):
        if success:
            self._status = "success"
            self._status_icon.setText("✓")
            self._status_icon.setStyleSheet(f"color: {COLOR_SUCCESS}; font-weight: bold;")
            self._time_label.setText(f"{elapsed:.1f}s")
        else:
            self._status = "error"
            self._status_icon.setText("✗")
            self._status_icon.setStyleSheet(f"color: {COLOR_ERROR}; font-weight: bold;")
            self._time_label.setText(f"{elapsed:.1f}s")

        self._result_label.setText(result)
        self._result_label.setVisible(True)

        if not success:
            self._result_label.setStyleSheet(f"color: {COLOR_ERROR};")

        self._apply_style()

    def set_status_running(self):
        self._status = "running"
        self._status_icon.setText("⟳")
        self._status_icon.setStyleSheet("")
        self._apply_style()
