import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from qgis.PyQt.QtCore import QObject, QThread, pyqtSignal

from .llm_client import LLMClient, LLMResponse
from .tool_registry import ToolRegistry, ConfirmResult
from .context_manager import ContextManager
from .file_source_manager import FileSourceManager, SourceDecision
from ..tools.batch_reproject import run_batch_reproject
from ..tools.batch_clip import run_batch_clip
from ..tools.buffer import run_buffer
from ..tools.overlay import run_overlay
from ..tools.attribute_query import run_attribute_query
from ..tools.spatial_query import run_spatial_query
from ..tools.raster_calculator import run_raster_calculator
from ..tools.format_convert import run_format_convert
from ..tools.batch_export import run_batch_export
from ..tools.statistics import run_statistics
from ..tools.field_calculator import run_field_calculator
from ..tools.dissolve import run_dissolve
from ..tools.merge_vector_layers import run_merge_vector_layers
from ..tools.centroids import run_centroids
from ..tools.convex_hull import run_convex_hull
from ..tools.boundary import run_boundary
from ..tools.multipart_to_singleparts import run_multipart_to_singleparts
from ..tools.symmetrical_difference import run_symmetrical_difference
from ..tools.extract_by_extent import run_extract_by_extent
from ..tools.delete_fields import run_delete_fields
from ..tools.rename_field import run_rename_field


logger = logging.getLogger("QgisAgent")

MAX_AGENT_LOOPS = 30
MAX_HISTORY_MESSAGES = 20

SYSTEM_PROMPT_TEMPLATE = """你是 QGIS Agent，一个专业的 GIS 助手。你运行在 QGIS 中。

## 你的能力
你可以调用以下 GIS 工具来帮助用户完成空间数据处理任务：
{tool_definitions}

## 当前项目状态
{project_context}

## 数据来源说明
{data_source}

## 工作方式
1. 理解用户的自然语言需求
2. 如果需求复杂，拆解为多个子任务
3. 逐步调用工具完成每个子任务
4. 向用户报告执行结果

## 规则
- 调用工具时，图层名称必须与项目中已有图层的名称完全匹配
- 批量操作前先告知用户将处理多少个图层
- 涉及文件覆盖或删除时，先询问用户确认
- 如果用户的需求超出你的工具范围，坦诚告知并建议替代方案
- 优先使用中文回复（如果用户使用中文）
- 图层名以 "[plugin] " 开头的，是用户通过插件导入的文件，已自动加载为临时图层
- 临时图层在对话结束后可能被清理，处理完成后提醒用户是否需要持久保存
"""


class _WorkerThread(QThread):
    """Background thread for LLM + tool execution loop."""

    text_chunk = pyqtSignal(str)
    text_done = pyqtSignal()
    tool_started = pyqtSignal(str, dict)
    tool_finished = pyqtSignal(str, bool, str, float)
    error = pyqtSignal(str)
    finished = pyqtSignal()
    confirm_overwrite = pyqtSignal(str)  # message → main thread
    confirm_response = pyqtSignal(bool, bool)  # confirmed, apply_to_all → worker
    ask_directory = pyqtSignal(str)  # message → main thread
    directory_response = pyqtSignal(str)  # directory path → worker

    def __init__(self, llm: LLMClient, registry: ToolRegistry,
                 context_mgr: ContextManager, file_source_mgr: FileSourceManager,
                 messages: List[Dict[str, Any]], messages_lock: threading.Lock,
                 parent=None):
        super().__init__(parent)
        self._llm = llm
        self._registry = registry
        self._context_mgr = context_mgr
        self._file_source_mgr = file_source_mgr
        self._messages = messages
        self._messages_lock = messages_lock
        self._abort = False
        self._confirm_loop = None
        self._confirm_result = ConfirmResult(confirmed=False)
        self._dir_loop = None
        self._dir_result = ""

    def abort(self):
        self._abort = True
        self._llm.abort()

    def _append_message(self, msg: Dict[str, Any]):
        with self._messages_lock:
            self._messages.append(msg)

    def _ask_user_confirm(self, message: str) -> ConfirmResult:
        """Ask user for overwrite confirmation. Called from worker thread, blocks until response."""
        from qgis.PyQt.QtCore import QEventLoop
        self._confirm_result = ConfirmResult(confirmed=False)
        self._confirm_loop = QEventLoop()
        self.confirm_overwrite.emit(message)
        self._confirm_loop.exec_()
        self._confirm_loop = None
        return self._confirm_result

    def _on_confirm_response(self, confirmed: bool, apply_to_all: bool):
        """Receive confirmation response from main thread."""
        self._confirm_result = ConfirmResult(confirmed=confirmed, apply_to_all=apply_to_all)
        if self._confirm_loop:
            self._confirm_loop.quit()

    def _ask_user_directory(self, message: str) -> str:
        """Ask user to select a directory. Called from worker thread, blocks until response."""
        from qgis.PyQt.QtCore import QEventLoop
        self._dir_result = ""
        self._dir_loop = QEventLoop()
        self.ask_directory.emit(message)
        self._dir_loop.exec_()
        self._dir_loop = None
        return self._dir_result

    def _on_directory_response(self, directory: str):
        """Receive directory selection response from main thread."""
        self._dir_result = directory
        if self._dir_loop:
            self._dir_loop.quit()

    def run(self):
        try:
            self._run_loop()
        except Exception as e:
            logger.exception("Agent engine error")
            self.error.emit(f"引擎异常: {str(e)}")
        finally:
            self.finished.emit()

    def _run_loop(self):
        for loop_count in range(MAX_AGENT_LOOPS):
            if self._abort:
                self.error.emit("用户中断")
                return

            system_prompt = self._build_system_prompt()
            messages = self._build_messages(system_prompt)

            response = LLMResponse()
            for chunk in self._llm.chat_stream(messages, self._registry.get_definitions()):
                if self._abort:
                    self.error.emit("用户中断")
                    return

                if chunk.error:
                    self.error.emit(chunk.error)
                    return

                if chunk.content:
                    response.content += chunk.content
                    self.text_chunk.emit(chunk.content)

                if chunk.reasoning_content:
                    response.reasoning_content += chunk.reasoning_content

                if chunk.tool_calls:
                    response.tool_calls = chunk.tool_calls

                if chunk.finish_reason:
                    response.finish_reason = chunk.finish_reason

            if response.finish_reason == "stop":
                if response.content:
                    assistant_msg = {"role": "assistant", "content": response.content}
                    if response.reasoning_content:
                        assistant_msg["reasoning_content"] = response.reasoning_content
                    self._append_message(assistant_msg)
                    self.text_done.emit()
                return

            if response.finish_reason == "tool_calls" and response.tool_calls:
                self.text_done.emit()

                # Add assistant message with tool_calls to history
                assistant_msg = {"role": "assistant", "content": response.content or ""}
                if response.reasoning_content:
                    assistant_msg["reasoning_content"] = response.reasoning_content
                assistant_msg["tool_calls"] = response.tool_calls
                self._append_message(assistant_msg)

                # Execute each tool call
                for tc in response.tool_calls:
                    if self._abort:
                        self.error.emit("用户中断")
                        return

                    tool_name = tc.get("function", {}).get("name", "")
                    tool_args = tc.get("function", {}).get("arguments", {})
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_args = {}

                    self.tool_started.emit(tool_name, dict(tool_args))

                    start_time = time.time()
                    result = self._registry.execute(tool_name, tool_args)
                    elapsed = time.time() - start_time

                    success = result.get("success", False)
                    msg = result.get("message", result.get("error", ""))
                    self.tool_finished.emit(tool_name, success, msg, elapsed)

                    # Add tool result to messages
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                    self._append_message(tool_msg)

                # Loop again for LLM to process tool results
                continue

            # No tool calls and no stop - unexpected
            self.text_done.emit()
            return

        self.error.emit(f"已达到最大循环次数 ({MAX_AGENT_LOOPS})，已停止")

    def _build_system_prompt(self) -> str:
        source_filter = self._get_source_filter()
        context_json = self._context_mgr.collect_context_json(source_filter)
        tool_defs_json = json.dumps(self._registry.get_definitions(), ensure_ascii=False, indent=2)
        source_desc = self._file_source_mgr.get_source_description()

        return SYSTEM_PROMPT_TEMPLATE.format(
            tool_definitions=tool_defs_json,
            project_context=context_json,
            data_source=source_desc,
        )

    def _get_source_filter(self) -> Optional[str]:
        decision = self._file_source_mgr.resolve_source()
        if decision == SourceDecision.USE_PROJECT:
            return "project"
        if decision == SourceDecision.USE_PLUGIN:
            return "plugin"
        return None

    def _build_messages(self, system_prompt: str) -> List[Dict[str, Any]]:
        messages = [{"role": "system", "content": system_prompt}]
        with self._messages_lock:
            history = self._messages[-MAX_HISTORY_MESSAGES:]
        messages.extend(history)
        return messages


class AgentEngine(QObject):
    """Agent engine orchestrating LLM calls and tool execution."""

    text_chunk = pyqtSignal(str)
    text_done = pyqtSignal()
    tool_started = pyqtSignal(str, dict)
    tool_finished = pyqtSignal(str, bool, str, float)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, llm_client: LLMClient, iface, file_source_mgr: FileSourceManager, parent=None):
        super().__init__(parent)
        self._llm = llm_client
        self._iface = iface
        self._context_mgr = ContextManager(iface)
        self._file_source_mgr = file_source_mgr
        self._registry = ToolRegistry()
        self._messages: List[Dict[str, Any]] = []
        self._messages_lock = threading.Lock()
        self._pending_text: Optional[str] = None
        self._pending_files: Optional[list] = None
        self._worker: Optional[_WorkerThread] = None

        self._register_tools()

    def _register_tools(self):
        self._registry.register("batch_reproject", run_batch_reproject)
        self._registry.register("batch_clip", run_batch_clip)
        self._registry.register("buffer", run_buffer)
        self._registry.register("overlay", run_overlay)
        self._registry.register("attribute_query", run_attribute_query)
        self._registry.register("spatial_query", run_spatial_query)
        self._registry.register("raster_calculator", run_raster_calculator)
        self._registry.register("format_convert", run_format_convert)
        self._registry.register("batch_export", run_batch_export)
        self._registry.register("statistics", run_statistics)
        self._registry.register("field_calculator", run_field_calculator)
        self._registry.register("dissolve", run_dissolve)
        self._registry.register("merge_vector_layers", run_merge_vector_layers)
        self._registry.register("centroids", run_centroids)
        self._registry.register("convex_hull", run_convex_hull)
        self._registry.register("boundary", run_boundary)
        self._registry.register("multipart_to_singleparts", run_multipart_to_singleparts)
        self._registry.register("symmetrical_difference", run_symmetrical_difference)
        self._registry.register("extract_by_extent", run_extract_by_extent)
        self._registry.register("delete_fields", run_delete_fields)
        self._registry.register("rename_field", run_rename_field)


    def run(self, user_text: str, attached_files: list = None):
        if not self._llm.is_configured:
            self.error.emit("请先在设置中配置 API Key")
            return

        if self._worker and self._worker.isRunning():
            self._pending_text = user_text
            self._pending_files = list(attached_files) if attached_files else None
            self._worker.abort()
            return

        self._do_run(user_text, attached_files)

    def _do_run(self, user_text: str, attached_files: list = None):
        if attached_files:
            loaded = self._file_source_mgr.load_all_to_qgis()
            if loaded:
                logger.info(f"Loaded plugin files: {loaded}")

        decision = self._file_source_mgr.resolve_source()
        if decision == SourceDecision.ASK_USER:
            from qgis.PyQt.QtWidgets import QMessageBox
            desc = self._file_source_mgr.get_source_description()
            reply = QMessageBox.question(
                None,
                "选择数据来源",
                f"{desc}\n\n选择「是」使用项目图层，选择「否」使用插件导入的文件",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                self._file_source_mgr.set_source_override("project")
            else:
                self._file_source_mgr.set_source_override("plugin")

        with self._messages_lock:
            self._messages.append({"role": "user", "content": user_text})

        self._worker = _WorkerThread(
            self._llm, self._registry, self._context_mgr,
            self._file_source_mgr, self._messages, self._messages_lock, self,
        )
        self._worker.text_chunk.connect(self.text_chunk)
        self._worker.text_done.connect(self.text_done)
        self._worker.tool_started.connect(self.tool_started)
        self._worker.tool_finished.connect(self.tool_finished)
        self._worker.error.connect(self.error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.confirm_overwrite.connect(self._on_confirm_overwrite)
        self._worker.confirm_response.connect(self._worker._on_confirm_response)
        self._worker.ask_directory.connect(self._on_ask_directory)
        self._worker.directory_response.connect(self._worker._on_directory_response)
        self._registry.set_confirm_callback(self._worker._ask_user_confirm)
        self._registry.set_ask_dir_callback(self._worker._ask_user_directory)
        self._worker.start()

    def abort(self):
        self._abort_current()

    def _abort_current(self):
        if self._worker and self._worker.isRunning():
            self._worker.abort()

    def _on_worker_finished(self):
        self._worker = None
        self.finished.emit()

        if self._pending_text is not None:
            text = self._pending_text
            files = self._pending_files
            self._pending_text = None
            self._pending_files = None
            self._do_run(text, files)

    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _on_confirm_overwrite(self, message: str):
        """Show overwrite confirmation dialog on main thread. Sends response back to worker."""
        from qgis.PyQt.QtWidgets import QMessageBox
        box = QMessageBox(
            QMessageBox.Question,
            "文件覆盖确认",
            message,
            QMessageBox.Yes | QMessageBox.No,
        )
        box.button(QMessageBox.Yes).setText("确认覆盖")
        box.button(QMessageBox.No).setText("取消")
        reply = box.exec_()
        if self._worker:
            self._worker.confirm_response.emit(reply == QMessageBox.Yes, False)

    def _on_ask_directory(self, message: str):
        """Show directory selection dialog on main thread. Sends selected path back to worker."""
        from qgis.PyQt.QtWidgets import QFileDialog
        directory = QFileDialog.getExistingDirectory(None, message, "")
        if self._worker:
            self._worker.directory_response.emit(directory)

    def clear_history(self):
        self._messages.clear()
