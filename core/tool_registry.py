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
    {
        "type": "function",
        "function": {
            "name": "field_calculator",
            "description": "使用 QGIS 表达式对矢量图层进行字段计算，可创建新字段或更新已有字段。支持数值、字符串、日期等字段类型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "输入矢量图层名称",
                    },
                    "field_name": {
                        "type": "string",
                        "description": "要创建或更新的字段名称",
                    },
                    "formula": {
                        "type": "string",
                        "description": "QGIS 表达式，如 '\"population\" * 1.1'、'length($geometry)'、'upper(\"name\")'",
                    },
                    "field_type": {
                        "type": "string",
                        "enum": ["float", "integer", "string", "date", "time", "datetime", "boolean"],
                        "description": "可选，字段类型，默认 float。适用于创建新字段时指定类型",
                    },
                    "field_length": {
                        "type": "integer",
                        "description": "可选，字段长度，默认 10",
                    },
                    "field_precision": {
                        "type": "integer",
                        "description": "可选，小数精度，默认 3（仅对 float 类型有效）",
                    },
                    "output_name": {
                        "type": "string",
                        "description": "可选，输出图层名称。不指定则命名为 '<原图层名>_calc_<字段名>'",
                    },
                },
                "required": ["layer_name", "field_name", "formula"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "topology_check",
            "description": "检查矢量图层的拓扑错误，输出包含错误要素的新图层。支持多种拓扑规则：面重叠、缝隙、悬挂节点、自相交等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "要检查的图层名称",
                    },
                    "rules": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "拓扑规则列表，支持简化名（如 'no_overlaps'）或 QGIS 原生规则名。不指定则检查所有适用规则",
                    },
                    "reference_layer": {
                        "type": "string",
                        "description": "跨图层规则的参考图层名称（如 point_in_polygon 需要指定面图层）",
                    },
                    "dangle_threshold": {
                        "type": "number",
                        "description": "悬挂节点长度阈值，小于此值的悬挂节点被标记为错误，默认 0.001",
                    },
                    "gap_tolerance": {
                        "type": "number",
                        "description": "缝隙容差，小于此值的缝隙被忽略，默认 0.0001",
                    },
                },
                "required": ["layer_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "topology_fix",
            "description": "修复矢量图层的拓扑错误，输出修复后的新图层（原图层不变）。支持修复：几何无效、自相交、重叠、缝隙等错误。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "要修复的图层名称",
                    },
                    "error_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要修复的错误类型列表（如 'invalid_geometry', 'self_intersection'）。不指定则修复所有可修复的错误",
                    },
                    "reference_layer": {
                        "type": "string",
                        "description": "跨图层规则的参考图层名称",
                    },
                    "dangle_threshold": {
                        "type": "number",
                        "description": "悬挂节点删除阈值，小于此值的悬挂节点被删除，默认 0.001",
                    },
                    "gap_tolerance": {
                        "type": "number",
                        "description": "缝隙填充容差，小于此值的缝隙被忽略，默认 0.0001",
                    },
                    "overlap_strategy": {
                        "type": "string",
                        "enum": ["trim", "merge"],
                        "description": "重叠处理策略：trim(裁剪) 或 merge(合并)，默认 trim",
                    },
                },
                "required": ["layer_name"],
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
