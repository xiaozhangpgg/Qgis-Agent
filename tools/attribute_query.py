import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsExpression, QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer

logger = logging.getLogger("QgisAgent")


def run_attribute_query(
    layer_name: str,
    expression: str,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Extract features from a layer by attribute expression.

    Args:
        layer_name: Input layer name.
        expression: QGIS expression string, e.g. '"population" > 10000'.

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

    if not isinstance(layer, QgsVectorLayer):
        return {"success": False, "error": f"图层 '{layer_name}' 不是矢量图层"}

    if not expression or not expression.strip():
        return {"success": False, "error": "查询表达式不能为空"}

    expr = QgsExpression(expression)
    if not expr.isValid():
        return {"success": False, "error": f"表达式语法错误: {expr.parserErrorString()}"}

    feature_count_before = max(layer.featureCount(), 0)

    try:
        params = {
            "INPUT": layer,
            "EXPRESSION": expression,
            "OUTPUT": "memory:",
        }

        result = processing.run("native:extractbyexpression", params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            safe_expr = expression.replace('"', "'")[:30]
            output_layer.setName(f"{layer_name}_query_{safe_expr}")

            feature_count_after = max(output_layer.featureCount(), 0)

            project.addMapLayer(output_layer)

            return {
                "success": True,
                "message": (
                    f"从 '{layer_name}' 中查询到 {feature_count_after} 个要素，"
                    f"表达式: {expression}"
                ),
                "results": [{
                    "input": layer_name,
                    "output": output_layer.name(),
                    "expression": expression,
                    "features_before": feature_count_before,
                    "features_after": feature_count_after,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Attribute query error for layer '{layer_name}'")
        return {"success": False, "error": f"属性查询失败: {str(e)}"}

