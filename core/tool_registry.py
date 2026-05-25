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
                        "description": "目标 CRS 的 EPSG 代码。地理坐标系: CGCS2000=EPSG:4490, WGS84=EPSG:4326, 北京54=EPSG:4214, 西安80=EPSG:4610。高斯-克吕格投影每带含带号(东移=带号×1000000+500000)和无带号/CM(东移=500000)两种变体，EPSG代码不同！CGCS2000 3度带: 含带号EPSG=4488+带号(如第39带=4527), 无带号EPSG=4509+带号(如第39带=4548); CGCS2000 6度带: 含带号EPSG=4478+带号(如第20带=4498), 无带号EPSG=4489+带号(如第20带=4509)。北京54 3度带: 含带号EPSG=2376+带号(如第39带=2415), 无带号EPSG=2397+带号(如第39带=2436); 北京54 6度带: 含带号EPSG=21400+带号(如第20带=21420), 无带号EPSG=21440+带号(如第20带=21460)。西安80 3度带: 含带号EPSG=2324+带号(如第39带=2363), 无带号EPSG=2345+带号(如第39带=2384); 西安80 6度带: 含带号EPSG=2314+带号(如第20带=2334), 无带号EPSG=2325+带号(如第20带=2345)。WGS84/UTM北半球: EPSG=32600+带号(如50N=32650)。3度带带号范围25-45(中央经线75°E-135°E)，6度带带号范围13-23(中央经线75°E-135°E)，UTM带号范围43-53。选择规则：用户说'第N带'通常指含带号(Y坐标前有带号如39500000)，说'中央经线'或'CM'通常指无带号(Y坐标为500000)。务必根据用户描述选择对应变体的EPSG代码，两种变体不可混用。",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["shp", "gpkg", "geojson", "kml", "csv"],
                        "description": "输出格式，默认 shp。shp=Shapefile, gpkg=GeoPackage, geojson=GeoJSON, kml=KML, csv=CSV",
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
            "description": "对图层中的要素创建指定距离的缓冲区。距离单位为米，若图层为地理坐标系（如 EPSG:4326）会自动重投影到投影坐标系后执行缓冲区分析，结果再重投影回原始坐标系。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "输入图层名称",
                    },
                    "distance": {
                        "type": "number",
                        "description": "缓冲区距离，单位为米",
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
                        "enum": ["intersects", "contains", "disjoint", "equals", "touches", "overlaps", "within", "crosses"],
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
                    "cellsize": {
                        "type": "number",
                        "description": "可选，输出像元大小，默认使用第一个输入栅格的像元大小",
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
            "description": "将图层直接导出为指定格式的文件。支持矢量格式（GeoJSON、GPKG、KML、CSV、SHP、GML、DXF、XLSX）和栅格格式（GeoTIFF、IMG）。用户需指定输出文件的完整路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer_name": {
                        "type": "string",
                        "description": "输入图层名称",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["geojson", "gpkg", "kml", "csv", "shp", "gml", "dxf", "xlsx", "geotiff", "tiff", "img"],
                        "description": "输出格式",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "输出文件的完整路径（由用户指定），如 'D:/output/roads.geojson'",
                    },
                    "target_crs": {
                        "type": "string",
                        "description": "可选，目标 CRS 的 EPSG 代码，如 'EPSG:4326'。不指定则保持原图层 CRS",
                    },
                    "only_selected": {
                        "type": "boolean",
                        "description": "可选，是否仅导出选中的要素，默认 false",
                    },
                },
                "required": ["layer_name", "output_format", "output_path"],
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
]


ConfirmCallback = Optional[Callable[[str], ConfirmResult]]
AskDirCallback = Optional[Callable[[str], str]]


class ToolRegistry:
    """Registry mapping tool names to Python functions and JSON Schema definitions."""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._definitions: List[Dict[str, Any]] = list(TOOL_DEFINITIONS)
        self._confirm_cb: ConfirmCallback = None
        self._ask_dir_cb: AskDirCallback = None

    def register(self, name: str, func: Callable):
        self._tools[name] = func

    def set_confirm_callback(self, callback: ConfirmCallback):
        """Set a callback for file overwrite confirmation. Called from worker thread."""
        self._confirm_cb = callback

    def set_ask_dir_callback(self, callback: AskDirCallback):
        """Set a callback for directory selection. Called from worker thread."""
        self._ask_dir_cb = callback

    @property
    def confirm_callback(self) -> ConfirmCallback:
        return self._confirm_cb

    @property
    def ask_dir_callback(self) -> AskDirCallback:
        return self._ask_dir_cb

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
            if self._ask_dir_cb:
                call_params["_ask_dir_callback"] = self._ask_dir_cb
            result = func(**call_params)
            return result
        except Exception as e:
            logger.exception(f"Tool '{name}' execution error")
            return {"success": False, "error": str(e)}

    def has_tool(self, name: str) -> bool:
        return name in self._tools
