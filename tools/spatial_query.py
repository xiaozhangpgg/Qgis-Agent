import logging
from typing import Any, Dict

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer

logger = logging.getLogger("QgisAgent")

VALID_PREDICATES = {
    "intersects": 0,
    "contains": 1,
    "disjoint": 2,
    "equals": 3,
    "touches": 4,
    "overlaps": 5,
    "within": 6,
    "crosses": 7,
}


def run_spatial_query(
    layer_name: str,
    reference_layer: str,
    predicate: str = "intersects",
) -> Dict[str, Any]:
    """Extract features from a layer based on spatial relationship with a reference layer.

    Args:
        layer_name: Input layer name.
        reference_layer: Reference layer name for spatial comparison.
        predicate: Spatial predicate: intersects, contains, disjoint, equals, touches, overlaps, within, crosses.

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
        return {"success": False, "error": f"图层 '{layer_name}' 不是矢量图层，无法执行空间查询"}

    ref = find_layer(reference_layer)
    if ref is None:
        return {"success": False, "error": f"参考图层 '{reference_layer}' 不存在"}
    if not isinstance(ref, QgsVectorLayer):
        return {"success": False, "error": f"参考图层 '{reference_layer}' 不是矢量图层，无法执行空间查询"}

    predicate = predicate.lower()
    if predicate not in VALID_PREDICATES:
        return {
            "success": False,
            "error": f"不支持的空间谓词 '{predicate}'，可选: {', '.join(VALID_PREDICATES.keys())}",
        }

    feature_count_before = layer.featureCount() if hasattr(layer, "featureCount") else -1
    if feature_count_before < 0:
        feature_count_before = "未知"

    try:
        params = {
            "INPUT": layer,
            "PREDICATE": [VALID_PREDICATES[predicate]],
            "INTERSECT": ref,
            "OUTPUT": "memory:",
        }

        result = processing.run("native:extractbylocation", params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            output_layer.setName(f"{layer_name}_spatial_{predicate}")
            project.addMapLayer(output_layer)

            feature_count_after = output_layer.featureCount()
            if feature_count_after < 0:
                feature_count_after = "未知"

            return {
                "success": True,
                "message": (
                    f"从 '{layer_name}' 中查询到 {feature_count_after} 个要素，"
                    f"空间关系: {predicate}，参考图层: '{reference_layer}'"
                ),
                "results": [{
                    "input": layer_name,
                    "reference": reference_layer,
                    "predicate": predicate,
                    "output": output_layer.name(),
                    "features_before": feature_count_before,
                    "features_after": feature_count_after,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Spatial query error for layer '{layer_name}'")
        return {"success": False, "error": f"空间查询失败: {str(e)}"}

