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
    {
        "type": "function",
        "function": {
            "name": "overlay",
            "description": "对两个矢量图层执行叠加分析（相交、联合、差异）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_a": {
                        "type": "string",
                        "description": "第一个图层名称（输入图层）",
                    },
                    "layer_b": {
                        "type": "string",
                        "description": "第二个图层名称（叠加图层）",
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["intersection", "union", "difference"],
                        "description": "叠加操作类型: intersection(相交), union(联合), difference(差异)",
                    },
                },
                "required": ["layer_a", "layer_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attribute_query",
            "description": "根据属性表达式从图层中提取满足条件的要素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "输入图层名称",
                    },
                    "expression": {
                        "type": "string",
                        "description": "QGIS 表达式，如 '\"population\" > 10000' 或 '\"type\" = \\'road\\''",
                    },
                },
                "required": ["layer_name", "expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spatial_query",
            "description": "根据空间关系从图层中提取要素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "输入图层名称",
                    },
                    "reference_layer": {
                        "type": "string",
                        "description": "参考图层名称",
                    },
                    "predicate": {
                        "type": "string",
                        "enum": ["intersects", "contains", "equals", "touches", "overlaps", "within", "crosses"],
                        "description": "空间关系谓词",
                    },
                },
                "required": ["layer_name", "reference_layer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "raster_calculator",
            "description": "使用表达式对栅格图层进行计算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "栅格计算表达式，如 '\"raster_a@1\" * 2'",
                    },
                    "input_rasters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "输入栅格图层名称列表",
                    },
                    "output_name": {
                        "type": "string",
                        "description": "可选，输出图层名称",
                    },
                },
                "required": ["expression", "input_rasters"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "format_convert",
            "description": "将矢量图层转换为其他格式（GeoJSON、GPKG、KML、CSV、SHP、GML）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "输入图层名称",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["geojson", "gpkg", "kml", "csv", "shp", "gml"],
                        "description": "输出格式",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "可选，输出目录路径。不指定则结果添加到当前项目",
                    },
                },
                "required": ["layer_name", "output_format"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "batch_export",
            "description": "批量将多个图层导出为指定格式的文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要导出的图层名称列表",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["geojson", "gpkg", "kml", "csv", "shp", "gml"],
                        "description": "输出格式",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "输出目录路径",
                    },
                },
                "required": ["layer_names", "output_format", "output_dir"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "statistics",
            "description": "对图层字段进行统计汇总，可按分类字段分组。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "输入图层名称",
                    },
                    "value_field": {
                        "type": "string",
                        "description": "要统计的数值字段名",
                    },
                    "category_field": {
                        "type": "string",
                        "description": "可选，按此字段分组统计",
                    },
                },
                "required": ["layer_name", "value_field"],
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
            call_params = dict(params)
            if self._confirm_cb:
                call_params["_confirm_callback"] = self._confirm_cb
            result = func(**call_params)
            return result
        except Exception as e:
            logger.exception(f"Tool '{name}' execution error")
            return {"success": False, "error": str(e)}

    def has_tool(self, name: str) -> bool:
        return name in self._tools
