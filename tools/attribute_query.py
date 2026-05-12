import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsProject

import processing

logger = logging.getLogger("QgisAgent")


def run_attribute_query(
    layer_name: str,
    expression: str,
    _confirm_callback: Optional[Callable] = None,
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

    layer = _find_layer(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    if not expression or not expression.strip():
        return {"success": False, "error": "查询表达式不能为空"}

    feature_count_before = layer.featureCount() if hasattr(layer, "featureCount") else 0

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
            project.addMapLayer(output_layer)

            feature_count_after = output_layer.featureCount()

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


def _find_layer(name: str):
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None
