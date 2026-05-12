from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QPushButton, QLabel, QMessageBox,
    QGroupBox,
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsSettings

from ..core.llm_client import LLMClient, PROVIDERS

SETTINGS_PREFIX = "QgisAgent"


def _s(key: str) -> str:
    return f"{SETTINGS_PREFIX}/{key}"


class SettingsDialog(QDialog):
    """Settings dialog for API Key, Provider, and Model configuration."""

    def __init__(self, llm_client: LLMClient, parent=None):
        super().__init__(parent)
        self._llm = llm_client
        self._loading = False
        self.setWindowTitle("QGIS Agent 设置")
        self.setMinimumWidth(480)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # --- Provider / Model group ---
        api_group = QGroupBox("API 配置")
        form = QFormLayout()

        self._provider_combo = QComboBox()
        for key, cfg in PROVIDERS.items():
            self._provider_combo.addItem(cfg.name, key)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self._provider_combo)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)

        self._fetch_models_btn = QPushButton("获取模型列表")
        self._fetch_models_btn.setFixedWidth(100)
        self._fetch_models_btn.clicked.connect(self._on_fetch_models)

        model_row = QHBoxLayout()
        model_row.addWidget(self._model_combo, 1)
        model_row.addWidget(self._fetch_models_btn)
        form.addRow("Model:", model_row)

        self._base_url_input = QLineEdit()
        self._base_url_input.setPlaceholderText("https://api.example.com/v1")
        form.addRow("Base URL:", self._base_url_input)

        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.Password)
        self._api_key_input.setPlaceholderText("输入 API Key")

        key_row = QHBoxLayout()
        key_row.addWidget(self._api_key_input)

        self._toggle_btn = QPushButton("显示")
        self._toggle_btn.setFixedWidth(50)
        self._toggle_btn.clicked.connect(self._toggle_api_key_visibility)
        key_row.addWidget(self._toggle_btn)

        form.addRow("API Key:", key_row)

        api_group.setLayout(form)
        layout.addWidget(api_group)

        # --- Test connection ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._test_btn = QPushButton("测试连接")
        self._test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(self._test_btn)

        layout.addLayout(btn_row)

        # --- Privacy notice ---
        notice = QLabel("注意：您的消息内容将发送到第三方 AI 服务进行处理。")
        notice.setWordWrap(True)
        notice.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(notice)

        # --- Dialog buttons ---
        layout.addStretch()

        self._btn_row = QHBoxLayout()
        self._btn_row.addStretch()

        self._save_btn = QPushButton("保存")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._save_and_accept)
        self._btn_row.addWidget(self._save_btn)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.clicked.connect(self.reject)
        self._btn_row.addWidget(self._cancel_btn)

        layout.addLayout(self._btn_row)

        # Initial state
        self._on_provider_changed()

    def _on_provider_changed(self):
        if self._loading:
            return

        key = self._provider_combo.currentData()
        cfg = PROVIDERS.get(key)
        if not cfg:
            return

        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        for m in cfg.models:
            self._model_combo.addItem(m)
        if cfg.default_model:
            self._model_combo.setCurrentText(cfg.default_model)
        self._model_combo.blockSignals(False)

        is_custom = key == "custom"
        self._base_url_input.setReadOnly(not is_custom)
        self._base_url_input.setEnabled(is_custom)
        if not is_custom:
            self._base_url_input.setText(cfg.base_url)
        else:
            self._base_url_input.setText("")

    def _toggle_api_key_visibility(self):
        if self._api_key_input.echoMode() == QLineEdit.Password:
            self._api_key_input.setEchoMode(QLineEdit.Normal)
            self._toggle_btn.setText("隐藏")
        else:
            self._api_key_input.setEchoMode(QLineEdit.Password)
            self._toggle_btn.setText("显示")

    def _on_fetch_models(self):
        self._apply_to_client()
        self._fetch_models_btn.setEnabled(False)
        self._fetch_models_btn.setText("获取中...")

        success, result = self._llm.fetch_models()

        self._fetch_models_btn.setEnabled(True)
        self._fetch_models_btn.setText("获取模型列表")

        if success:
            current_text = self._model_combo.currentText()
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            self._model_combo.addItems(result)
            if current_text and current_text in result:
                self._model_combo.setCurrentText(current_text)
            elif self._model_combo.count() > 0:
                self._model_combo.setCurrentIndex(0)
            self._model_combo.blockSignals(False)
        else:
            QMessageBox.warning(self, "获取失败", result)

    def _test_connection(self):
        self._apply_to_client()
        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中...")

        success, msg = self._llm.test_connection()

        self._test_btn.setEnabled(True)
        self._test_btn.setText("测试连接")

        if success:
            QMessageBox.information(self, "测试结果", msg)
        else:
            QMessageBox.warning(self, "测试结果", msg)

    def _apply_to_client(self):
        provider_key = self._provider_combo.currentData()
        api_key = self._api_key_input.text().strip()
        model = self._model_combo.currentText().strip()
        base_url = self._base_url_input.text().strip() or None
        self._llm.configure(provider_key, api_key, model, base_url)

    def _save_and_accept(self):
        provider_key = self._provider_combo.currentData()
        api_key = self._api_key_input.text().strip()
        model = self._model_combo.currentText().strip()
        base_url = self._base_url_input.text().strip()

        if not api_key:
            QMessageBox.warning(self, "错误", "请输入 API Key")
            return

        settings = QgsSettings()
        settings.setValue(_s("provider"), provider_key)
        settings.setValue(_s("api_key"), api_key)
        settings.setValue(_s("model"), model)
        settings.setValue(_s("base_url"), base_url)

        self._apply_to_client()
        self.accept()

    def _load_settings(self):
        self._loading = True
        settings = QgsSettings()

        provider_key = settings.value(_s("provider"), "deepseek")
        api_key = settings.value(_s("api_key"), "")
        model = settings.value(_s("model"), "")
        base_url = settings.value(_s("base_url"), "")

        idx = self._provider_combo.findData(provider_key)
        if idx >= 0:
            self._provider_combo.setCurrentIndex(idx)

        self._on_provider_changed()

        if model:
            self._model_combo.setCurrentText(model)

        if base_url:
            self._base_url_input.setText(base_url)

        self._api_key_input.setText(api_key)

        self._loading = False

        self._apply_to_client()
