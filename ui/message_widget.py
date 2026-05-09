from qgis.PyQt.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QSizePolicy, QApplication,
)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QColor, QPalette


def _palette_color(role: QPalette.ColorRole) -> QColor:
    return QApplication.palette().color(role)


class UserMessageWidget(QFrame):
    """User message block - right-aligned with highlight tint background."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._init_ui(text)

    def _init_ui(self, text: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        highlight = _palette_color(QPalette.Highlight)
        bg = QColor(highlight)
        bg.setAlpha(25)

        self.setStyleSheet(
            f"UserMessageWidget {{ background: {bg.name()}; border-radius: 4px; }}"
        )

        layout.addWidget(label)
        self.setAlignment(Qt.AlignRight)

    def setAlignment(self, alignment):
        self.layout().setAlignment(alignment)


class AiMessageWidget(QFrame):
    """AI message block - left-aligned with subtle background, supports streaming."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._full_text = ""
        self._cursor_visible = True
        self._init_ui()
        self._start_cursor_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        is_dark = self._is_dark_theme()
        bg = "#2D2D2D" if is_dark else "#F5F5F5"

        self.setStyleSheet(
            f"AiMessageWidget {{ background: {bg}; border-radius: 4px; }}"
        )

        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._label.setOpenExternalLinks(True)
        layout.addWidget(self._label)

        self.layout().setAlignment(Qt.AlignLeft)

    def _is_dark_theme(self) -> bool:
        bg = _palette_color(QPalette.Window)
        return bg.lightness() < 128

    def _start_cursor_timer(self):
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._cursor_timer.start(500)
        self.destroyed.connect(self._cursor_timer.stop)

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self._update_display()

    def append_text(self, chunk: str):
        self._full_text += chunk
        self._update_display()

    def set_text(self, text: str):
        self._full_text = text
        self._update_display()

    def set_error(self, error_text: str):
        self._full_text += f"\n⚠ {error_text}"
        self._update_display()
        self._label.setStyleSheet("QLabel { color: #F44336; }")

    def stop_cursor(self):
        self._cursor_timer.stop()
        self._cursor_visible = False
        self._update_display()

    def _update_display(self):
        display = self._full_text
        if self._cursor_visible and self._cursor_timer.isActive():
            display += "▌"
        self._label.setText(self._format_text(display))

    def _format_text(self, text: str) -> str:
        """Basic Markdown-like formatting for display."""
        import re

        base_color = _palette_color(QPalette.Base).name()

        # Code blocks
        text = re.sub(
            r'```(\w*)\n(.*?)```',
            lambda m: f'<pre style="background: {base_color}; padding: 8px; border-radius: 3px; font-family: Consolas, Monaco, monospace;">{m.group(2)}</pre>',
            text,
            flags=re.DOTALL,
        )

        # Inline code
        text = re.sub(
            r'`([^`]+)`',
            rf'<code style="background: {base_color}; padding: 1px 4px; border-radius: 2px; font-family: Consolas, Monaco, monospace;">\1</code>',
            text,
        )

        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

        # Headings
        text = re.sub(r'^### (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<b style="font-size: 14px;">\1</b>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<b style="font-size: 16px;">\1</b>', text, flags=re.MULTILINE)

        # Lists
        text = re.sub(r'^[-*] (.+)$', r'• \1', text, flags=re.MULTILINE)

        # Newlines
        text = text.replace('\n', '<br>')

        return text
