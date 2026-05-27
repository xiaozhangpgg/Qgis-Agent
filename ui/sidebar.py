import os

from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QLineEdit,
    QSizePolicy, QFileDialog, QFrame, QTextEdit,
    QMessageBox, QMenu,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QKeyEvent

from .message_widget import UserMessageWidget, AiMessageWidget
from .tool_card import ToolCardWidget
from ..core.llm_client import LLMClient
from ..core.agent_engine import AgentEngine
from ..core.conversation_manager import ConversationManager
from ..core.file_source_manager import FileSourceManager
from .settings_dialog import SettingsDialog


class MessageInput(QTextEdit):
    """Multi-line input with Enter to send, Shift+Enter for newline."""
    submit = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("输入消息...")
        self.setMinimumHeight(36)
        self.setMaximumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.textChanged.connect(self._auto_resize)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                if self.toPlainText().strip():
                    self.submit.emit()
                return
        super().keyPressEvent(event)

    def _auto_resize(self):
        doc = self.document()
        height = int(doc.size().height()) + 10
        self.setMinimumHeight(min(max(36, height), 120))


class SidebarWidget(QDockWidget):
    """QGIS Agent sidebar - QDockWidget with chat interface."""

    def __init__(self, iface, llm_client: LLMClient, parent=None):
        super().__init__("QGIS Agent", parent)
        self.iface = iface
        self._llm = llm_client
        self._conversation_mgr = ConversationManager()
        self._file_source_mgr = FileSourceManager(iface)
        self._engine = AgentEngine(llm_client, iface, self._file_source_mgr)

        self._attached_files = []
        self._tool_cards = []
        self._current_ai_msg = None
        self._current_ai_text = ""
        self._current_view = "chat"  # "chat" or "history"
        self._message_count = 0

        self.setObjectName("QgisAgentSidebar")
        self.setMinimumWidth(300)
        self._main_window = parent
        self.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
        )

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        container = QWidget()
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # --- Top bar ---
        self._top_bar = self._create_top_bar()
        self._main_layout.addWidget(self._top_bar)

        # --- Stacked views: chat and history ---
        self._chat_view = self._create_chat_view()
        self._history_view = self._create_history_view()

        self._main_layout.addWidget(self._chat_view)
        self._main_layout.addWidget(self._history_view)
        self._history_view.hide()

        self._main_layout.setStretch(1, 1)

        self.setWidget(container)

    def _create_top_bar(self):
        bar = QFrame()
        bar.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)

        self._title_label = QLabel("QGIS Agent")
        self._title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._title_label)

        layout.addStretch()

        self._new_chat_btn = QPushButton("新对话")
        self._new_chat_btn.setToolTip("创建新对话")
        layout.addWidget(self._new_chat_btn)

        self._history_btn = QPushButton("历史")
        self._history_btn.setToolTip("查看对话历史")
        layout.addWidget(self._history_btn)

        self._settings_btn = QPushButton("设置")
        self._settings_btn.setToolTip("API 设置")
        layout.addWidget(self._settings_btn)

        return bar

    def _create_chat_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Message area
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._messages_container = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_container)
        self._messages_layout.setContentsMargins(8, 8, 8, 8)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch()

        self._scroll_area.setWidget(self._messages_container)
        layout.addWidget(self._scroll_area, 1)

        # File attachment area (hidden by default)
        self._file_area = QFrame()
        self._file_area.setFrameShape(QFrame.StyledPanel)
        self._file_area_layout = QHBoxLayout(self._file_area)
        self._file_area_layout.setContentsMargins(8, 4, 8, 4)
        self._file_area_layout.setSpacing(4)
        self._file_area.setVisible(False)
        layout.addWidget(self._file_area)

        # Input area
        input_frame = QFrame()
        input_frame.setFrameShape(QFrame.StyledPanel)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 4, 8, 4)

        self._add_file_btn = QPushButton("📎")
        self._add_file_btn.setToolTip("添加文件")
        self._add_file_btn.setFixedSize(32, 32)
        input_layout.addWidget(self._add_file_btn)

        self._input = MessageInput()
        input_layout.addWidget(self._input, 1)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedHeight(36)
        self._send_btn.setEnabled(False)
        self._send_btn.setStyleSheet(
            "QPushButton:disabled { color: gray; }"
        )
        input_layout.addWidget(self._send_btn)

        layout.addWidget(input_frame)

        return view

    def _create_history_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Back button
        back_row = QHBoxLayout()
        self._back_btn = QPushButton("← 返回")
        back_row.addWidget(self._back_btn)
        back_row.addStretch()
        layout.addLayout(back_row)

        # Search box
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索对话...")
        layout.addWidget(self._search_input)

        # History list (scroll area)
        self._history_scroll = QScrollArea()
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._history_container = QWidget()
        self._history_list_layout = QVBoxLayout(self._history_container)
        self._history_list_layout.setContentsMargins(0, 0, 0, 0)
        self._history_list_layout.setSpacing(4)
        self._history_list_layout.addStretch()

        self._history_scroll.setWidget(self._history_container)
        layout.addWidget(self._history_scroll, 1)

        return view

    def _connect_signals(self):
        self._send_btn.clicked.connect(self._on_send)
        self._input.submit.connect(self._on_send)
        self._input.textChanged.connect(self._on_input_changed)
        self._add_file_btn.clicked.connect(self._on_add_file)
        self._new_chat_btn.clicked.connect(self._on_new_chat)
        self._history_btn.clicked.connect(self._on_show_history)
        self._back_btn.clicked.connect(self._on_show_chat)
        self._settings_btn.clicked.connect(self._on_open_settings)
        self._search_input.textChanged.connect(self._on_search)

        self._engine.text_chunk.connect(self._on_ai_text_chunk)
        self._engine.text_done.connect(self._on_ai_text_done)
        self._engine.tool_started.connect(self._on_tool_started)
        self._engine.tool_finished.connect(self._on_tool_finished)
        self._engine.error.connect(self._on_error)
        self._engine.finished.connect(self._on_engine_finished)

    def _on_input_changed(self):
        has_text = bool(self._input.toPlainText().strip())
        self._send_btn.setEnabled(has_text)

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if not text:
            return

        self._add_user_message(text)
        self._input.clear()
        self._set_input_enabled(False)

        # Ensure conversation exists
        conv_id = self._conversation_mgr.get_current_id()
        if not conv_id:
            conv_id = self._conversation_mgr.create_new()

        # Save user message
        self._conversation_mgr.save_message(conv_id, "user", text)
        self._message_count += 1

        # Auto-generate title after first user message
        if self._message_count == 1:
            title = text[:20] + ("..." if len(text) > 20 else "")
            self._conversation_mgr.update_title(conv_id, title)

        # Persist plugin file paths in conversation metadata (AC-03C-12)
        if self._attached_files:
            file_paths = [f.file_path for f in self._attached_files]
            self._conversation_mgr.update_metadata(
                conv_id, {"plugin_files": file_paths}
            )

        self._current_ai_text = ""

        files = list(self._attached_files)
        self._clear_attached_files()

        self._engine.run(text, files)

    def _add_user_message(self, text):
        msg = UserMessageWidget(text)
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, msg)
        self._scroll_to_bottom()

    def _add_ai_message_widget(self):
        msg = AiMessageWidget()
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, msg)
        self._current_ai_msg = msg
        return msg

    def _on_ai_text_chunk(self, chunk: str):
        if not hasattr(self, '_current_ai_msg') or self._current_ai_msg is None:
            self._add_ai_message_widget()
        self._current_ai_msg.append_text(chunk)
        self._current_ai_text += chunk
        self._scroll_to_bottom()

    def _on_ai_text_done(self):
        if self._current_ai_text:
            conv_id = self._conversation_mgr.get_current_id()
            if conv_id:
                self._conversation_mgr.save_message(conv_id, "assistant", self._current_ai_text)
            self._current_ai_text = ""
        if self._current_ai_msg:
            self._current_ai_msg.stop_cursor()
        self._current_ai_msg = None

    def _on_tool_started(self, tool_name: str, params: dict):
        card = ToolCardWidget(tool_name, params)
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, card)
        self._tool_cards.append(card)
        self._scroll_to_bottom()

    def _on_tool_finished(self, tool_name: str, success: bool, result: str, elapsed: float):
        if self._tool_cards:
            card = self._tool_cards[-1]
            card.set_result(success, result, elapsed)
        self._scroll_to_bottom()

    def _on_error(self, error_msg: str):
        if not hasattr(self, '_current_ai_msg') or self._current_ai_msg is None:
            self._add_ai_message_widget()
        self._current_ai_msg.append_text(f"\n⚠ {error_msg}")
        self._current_ai_msg.stop_cursor()
        self._current_ai_msg = None
        self._set_input_enabled(True)

    def _on_engine_finished(self):
        if not self._engine.is_busy:
            self._set_input_enabled(True)
            self._tool_cards = []

    def _set_input_enabled(self, enabled: bool):
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled and bool(self._input.toPlainText().strip()))
        self._add_file_btn.setEnabled(enabled)

    def _scroll_to_bottom(self):
        scrollbar = self._scroll_area.verticalScrollBar()
        # Only auto-scroll if user is already near the bottom (within 50px)
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 50
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _on_add_file(self):
        file_filter = (
            "矢量文件 (*.shp *.geojson *.gpkg *.kml *.tab);;"
            "栅格文件 (*.tif *.tiff *.img *.asc);;"
            "所有文件 (*)"
        )
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "", file_filter
        )
        if not files:
            return

        for f in files:
            managed = self._file_source_mgr.add_file(f)
            if managed:
                self._attached_files.append(managed)
                self._add_file_tag(managed.display_name, managed)

        self._file_area.setVisible(bool(self._attached_files))

    def _add_file_tag(self, name: str, managed_file):
        from qgis.PyQt.QtGui import QPalette
        from qgis.PyQt.QtWidgets import QApplication
        mid_color = QApplication.palette().color(QPalette.Mid).name()
        tag = QFrame()
        tag.setStyleSheet(f"QFrame {{ background: {mid_color}; border-radius: 3px; }}")
        layout = QHBoxLayout(tag)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        label = QLabel(name)
        label.setStyleSheet("font-size: 12px;")
        layout.addWidget(label)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setStyleSheet("border: none; font-weight: bold;")
        remove_btn.clicked.connect(lambda: self._remove_file_tag(tag, managed_file))
        layout.addWidget(remove_btn)

        self._file_area_layout.addWidget(tag)

    def _remove_file_tag(self, tag_widget, managed_file):
        self._file_source_mgr.remove_file(managed_file.display_name)
        if managed_file in self._attached_files:
            self._attached_files.remove(managed_file)
        tag_widget.deleteLater()
        self._file_area.setVisible(bool(self._attached_files))

    def _clear_attached_files(self):
        self._file_source_mgr.clear_all()
        self._attached_files.clear()
        while self._file_area_layout.count():
            child = self._file_area_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._file_area.setVisible(False)

    def _on_new_chat(self):
        # Confirm temp layer cleanup if plugin files exist (AC-03C-11)
        if self._file_source_mgr.has_files():
            reply = QMessageBox.question(
                self,
                "新建对话",
                "当前有插件导入的文件，新建对话将移除这些临时图层。是否继续？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._clear_messages()
        self._clear_attached_files()
        self._conversation_mgr.create_new()
        self._current_ai_msg = None
        self._current_ai_text = ""
        self._tool_cards = []
        self._message_count = 0

    def _on_show_history(self):
        self._current_view = "history"
        self._chat_view.hide()
        self._history_view.show()
        self._refresh_history_list()

    def _on_show_chat(self):
        self._current_view = "chat"
        self._history_view.hide()
        self._chat_view.show()

    def _on_open_settings(self):
        dlg = SettingsDialog(self._llm, self)
        dlg.exec_()

    def _on_search(self, query: str):
        self._refresh_history_list(query.strip())

    def _refresh_history_list(self, query: str = ""):
        while self._history_list_layout.count() > 1:
            child = self._history_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if query:
            summaries = self._conversation_mgr.search_conversations(query)
        else:
            summaries = self._conversation_mgr.list_conversations()
        for s in summaries:
            item = self._create_history_item(s)
            self._history_list_layout.insertWidget(
                self._history_list_layout.count() - 1, item
            )

    def _create_history_item(self, summary):
        item = QFrame()
        item.setFrameShape(QFrame.StyledPanel)
        item.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(item)
        layout.setContentsMargins(8, 6, 8, 6)

        title_row = QHBoxLayout()
        title = QLabel(summary.title)
        title.setStyleSheet("font-weight: bold;")
        title_row.addWidget(title)
        title_row.addStretch()

        time_label = QLabel(summary.updated_at_display)
        time_label.setStyleSheet("color: gray; font-size: 11px;")
        title_row.addWidget(time_label)
        layout.addLayout(title_row)

        if summary.preview:
            preview = QLabel(summary.preview)
            preview.setStyleSheet("color: gray;")
            preview.setMaximumHeight(20)
            layout.addWidget(preview)

        def on_mouse_press(event):
            if event.button() == Qt.LeftButton:
                self._load_conversation(summary.id)
            elif event.button() == Qt.RightButton:
                menu = QMenu(self)
                delete_action = menu.addAction("删除")
                delete_action.triggered.connect(lambda: self._delete_conversation(summary.id))
                menu.exec_(event.globalPos())

        item.mousePressEvent = on_mouse_press
        return item

    def _delete_conversation(self, conv_id: str):
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除这条对话吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._conversation_mgr.delete_conversation(conv_id)
            self._refresh_history_list()

    def _load_conversation(self, conv_id):
        conv = self._conversation_mgr.load_conversation(conv_id)
        if not conv:
            return

        self._clear_messages()
        self._clear_attached_files()
        self._current_ai_text = ""
        self._message_count = 0

        # Restore plugin files from conversation metadata (AC-03C-12)
        plugin_files = conv.metadata.get("plugin_files", [])
        for fpath in plugin_files:
            if os.path.isfile(fpath):
                managed = self._file_source_mgr.add_file(fpath)
                if managed:
                    self._attached_files.append(managed)
                    self._add_file_tag(managed.display_name, managed)
        self._file_area.setVisible(bool(self._attached_files))

        for msg in conv.messages:
            if msg.role == "user":
                self._add_user_message(msg.content)
                self._message_count += 1
            elif msg.role == "assistant":
                ai_widget = self._add_ai_message_widget()
                ai_widget.set_text(msg.content)
                ai_widget.stop_cursor()
                self._current_ai_msg = None

        self._on_show_chat()

    def _clear_messages(self):
        while self._messages_layout.count() > 1:
            child = self._messages_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def showEvent(self, event):
        super().showEvent(event)

    def resizeEvent(self, event):
        if self._main_window:
            max_w = self._main_window.width() // 2
            if self.width() > max_w:
                self.resize(max_w, self.height())
        super().resizeEvent(event)

    def closeEvent(self, event):
        self._engine.abort()
        super().closeEvent(event)
