import logging
from typing import Any, Dict, Optional

from qgis.core import QgsProject

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")

_FIELD_TYPE_MAP = {
    "float": 0,
    "integer": 1,
    "string": 2,
    "date": 3,
    "time": 4,
    "datetime": 5,
    "boolean": 6,
}

_TYPE_DEFAULTS = {
    "float": {"length": 10, "precision": 3},
    "integer": {"length": 10, "precision": 0},
    "string": {"length": 50, "precision": 0},
    "date": {"length": 10, "precision": 0},
    "time": {"length": 8, "precision": 0},
    "datetime": {"length": 19, "precision": 0},
    "boolean": {"length": 1, "precision": 0},
}


def run_field_calculator(
    layer_name: str,
    field_name: str,
    formula: str,
    field_type: Optional[str] = None,
    field_length: Optional[int] = None,
    field_precision: Optional[int] = None,
    output_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate or update a field using a QGIS expression.

    Args:
        layer_name: Input vector layer name.
        field_name: Name of the field to create or update.
        formula: QGIS expression string.
        field_type: Optional field type (float/integer/string/date/time/datetime/boolean).
        field_length: Optional field length (default 10).
        field_precision: Optional decimal precision (default 3).
        output_name: Optional output layer name.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    layer = find_layer(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    if not formula or not formula.strip():
        return {"success": False, "error": "计算表达式不能为空"}

    resolved_type = field_type if field_type else "float"
    if resolved_type not in _FIELD_TYPE_MAP:
        valid = ", ".join(_FIELD_TYPE_MAP.keys())
        return {"success": False, "error": f"不支持的字段类型 '{resolved_type}'，可选: {valid}"}

    defaults = _TYPE_DEFAULTS.get(resolved_type, _TYPE_DEFAULTS["float"])
    length = field_length if field_length is not None else defaults["length"]
    precision = field_precision if field_precision is not None else defaults["precision"]

    try:
        params = {
            "INPUT": layer,
            "FIELD_NAME": field_name,
            "FIELD_TYPE": _FIELD_TYPE_MAP[resolved_type],
            "FIELD_LENGTH": length,
            "FIELD_PRECISION": precision,
            "FORMULA": formula,
            "OUTPUT": "memory:",
        }

        result = processing.run("native:fieldcalculator", params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            out_name = resolve_output_name(
                project, output_name or f"{layer_name}_calc_{field_name}"
            )
            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            return {
                "success": True,
                "message": f"字段计算完成：在 '{layer_name}' 上计算字段 '{field_name}'，公式: {formula}",
                "results": [{
                    "input": layer_name,
                    "output": out_name,
                    "field_name": field_name,
                    "formula": formula,
                    "field_type": resolved_type,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Field calculator error for layer '{layer_name}'")
        return {"success": False, "error": f"字段计算失败: {str(e)}"}

