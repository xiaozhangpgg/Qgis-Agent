import logging
import time
from typing import Any, Callable, Dict, List, Optional

from qgis.core import QgsProject

import processing

from ._utils import find_layer

logger = logging.getLogger("QgisAgent")

VALID_OPERATIONS = {
    "intersection": "native:intersection",
    "union": "native:union",
    "difference": "native:difference",
}


def run_overlay(
    layer_a: str,
    layer_b: str,
    operation: str = "intersection",
    _confirm_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Perform overlay analysis between two vector layers.

    Args:
        layer_a: Name of the first (input) layer.
        layer_b: Name of the second (overlay) layer.
        operation: One of 'intersection', 'union', 'difference'.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except AttributeError:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    if operation not in VALID_OPERATIONS:
        return {
            "success": False,
            "error": f"不支持的操作类型 '{operation}'，可选: {', '.join(VALID_OPERATIONS.keys())}",
        }

    input_layer = find_layer(layer_a)
    if input_layer is None:
        return {"success": False, "error": f"图层 '{layer_a}' 不存在"}

    overlay_layer = find_layer(layer_b)
    if overlay_layer is None:
        return {"success": False, "error": f"图层 '{layer_b}' 不存在"}

    if layer_a == layer_b and operation != "union":
        return {"success": False, "error": f"非 union 操作不能对同一图层执行"}

    if input_layer.crs() != overlay_layer.crs():
        return {
            "success": False,
            "error": (
                f"图层 CRS 不一致: '{layer_a}' 为 {input_layer.crs().authid()}, "
                f"'{layer_b}' 为 {overlay_layer.crs().authid()}"
            ),
        }

    if not input_layer.wkbType() or not overlay_layer.wkbType():
        return {"success": False, "error": "图层几何类型无效，无法执行叠加分析"}

    feature_count_a = input_layer.featureCount() if hasattr(input_layer, "featureCount") else 0
    feature_count_b = overlay_layer.featureCount() if hasattr(overlay_layer, "featureCount") else 0

    try:
        alg_id = VALID_OPERATIONS[operation]
        params = {
            "INPUT": input_layer,
            "OVERLAY": overlay_layer,
            "OUTPUT": "memory:",
        }

        result = processing.run(alg_id, params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            output_name = f"{layer_a}_{operation}_{layer_b}_{int(time.time())}"
            output_layer.setName(output_name)
            project.addMapLayer(output_layer)

            feature_count_after = output_layer.featureCount()

            op_label = {"intersection": "相交", "union": "联合", "difference": "差异"}[operation]
            return {
                "success": True,
                "message": (
                    f"叠加分析（{op_label}）完成，"
                    f"输入 '{layer_a}' 与 '{layer_b}' 处理后得到 {feature_count_after} 个要素"
                ),
                "results": [{
                    "input_a": layer_a,
                    "input_b": layer_b,
                    "operation": operation,
                    "output": output_layer.name(),
                    "features_input_a": feature_count_a,
                    "features_input_b": feature_count_b,
                    "features_output": feature_count_after,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Overlay error: {operation} between '{layer_a}' and '{layer_b}'")
        return {"success": False, "error": f"叠加分析失败: {str(e)}"}

