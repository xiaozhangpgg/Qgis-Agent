import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("QgisAgent")


@dataclass
class ConfirmResult:
    """Result of a user confirmation prompt."""
    confirmed: bool
    apply_to_all: bool = False

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "batch_reproject",
            "description": "批量将多个图层转换到指定的目标坐标参考系统 (CRS)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要转换的图层名称列表",
                    },
                    "target_crs": {
                        "type": "string",
                        "description": "目标 CRS，如 'EPSG:4490'、'EPSG:3857'",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "可选，输出目录路径。不指定则结果添加到当前项目",
                    },
                },
                "required": ["layer_names", "target_crs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "batch_clip",
            "description": "使用裁剪边界图层批量裁剪多个图层。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要裁剪的图层名称列表",
                    },
                    "clip_layer": {
                        "type": "string",
                        "description": "裁剪边界图层的名称",
                    },
                },
                "required": ["layer_names", "clip_layer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buffer",
            "description": "对图层中的要素创建指定距离的缓冲区。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "输入图层名称",
                    },
                    "distance": {
                        "type": "number",
                        "description": "缓冲区距离（单位与图层 CRS 一致）",
                    },
                    "segments": {
                        "type": "integer",
                        "description": "可选，圆弧段数，默认 25",
                    },
                    "dissolve": {
                        "type": "boolean",
                        "description": "可选，是否溶解重叠缓冲区，默认 false",
                    },
                },
                "required": ["layer_name", "distance"],
            },
        },
    },
]


ConfirmCallback = Optional[Callable[[str], ConfirmResult]]


class ToolRegistry:
    """Registry mapping tool names to Python functions and JSON Schema definitions."""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._definitions: List[Dict[str, Any]] = list(TOOL_DEFINITIONS)
        self._confirm_cb: ConfirmCallback = None

    def register(self, name: str, func: Callable):
        self._tools[name] = func

    def set_confirm_callback(self, callback: ConfirmCallback):
        """Set a callback for file overwrite confirmation. Called from worker thread."""
        self._confirm_cb = callback

    @property
    def confirm_callback(self) -> ConfirmCallback:
        return self._confirm_cb

    def get_definitions(self) -> List[Dict[str, Any]]:
        return self._definitions

    def execute(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        func = self._tools.get(name)
        if func is None:
            return {"success": False, "error": f"未知工具: {name}"}

        try:
            if self._confirm_cb:
                params["_confirm_callback"] = self._confirm_cb
            result = func(**params)
            return result
        except Exception as e:
            logger.exception(f"Tool '{name}' execution error")
            return {"success": False, "error": str(e)}

    def has_tool(self, name: str) -> bool:
        return name in self._tools
