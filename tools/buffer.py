import logging
from typing import Any, Dict, Optional

from qgis.core import (
    QgsProject,
    QgsApplication,
)

logger = logging.getLogger("QgisAgent")


def run_buffer(
    layer_name: str,
    distance: float,
    segments: int = 25,
    dissolve: bool = False,
) -> Dict[str, Any]:
    """Create buffer zones around features in a layer.

    Args:
        layer_name: Input layer name.
        distance: Buffer distance (units match layer CRS).
        segments: Number of segments for quarter circle (default 25).
        dissolve: Whether to dissolve overlapping buffers (default False).

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()
    processing = QgsApplication.processingRegistry()

    if not processing:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    layer = _find_layer(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    if distance <= 0:
        return {"success": False, "error": f"缓冲区距离必须大于 0，当前值: {distance}"}

    feature_count_before = layer.featureCount() if hasattr(layer, 'featureCount') else 0

    try:
        params = {
            "INPUT": layer,
            "DISTANCE": distance,
            "SEGMENTS": segments,
            "END_CAP_STYLE": 0,  # Round
            "JOIN_STYLE": 0,     # Round
            "MITER_LIMIT": 2,
            "DISSOLVE": dissolve,
            "OUTPUT": "memory:",
        }

        result = processing.run("native:buffer", params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            output_layer.setName(f"{layer_name}_buffer_{int(distance)}")
            project.addMapLayer(output_layer)

            feature_count_after = output_layer.featureCount()

            return {
                "success": True,
                "message": (
                    f"成功为 '{layer_name}' 创建 {distance} 单位缓冲区，"
                    f"生成 {feature_count_after} 个要素"
                ),
                "results": [{
                    "input": layer_name,
                    "output": output_layer.name(),
                    "distance": distance,
                    "features_before": feature_count_before,
                    "features_after": feature_count_after,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Buffer error for layer '{layer_name}'")
        return {"success": False, "error": f"缓冲区分析失败: {str(e)}"}


def _find_layer(name: str):
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None
