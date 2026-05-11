import logging
from typing import Any, Callable, Dict, List, Optional

from qgis.core import (
    QgsProject,
)

import processing

logger = logging.getLogger("QgisAgent")


def run_batch_clip(
    layer_names: List[str],
    clip_layer: str,
    _confirm_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Batch clip multiple layers by a clip boundary layer.

    Args:
        layer_names: List of layer names to clip.
        clip_layer: Name of the clip boundary layer.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    boundary = _find_layer(clip_layer)
    if boundary is None:
        return {"success": False, "error": f"裁剪边界图层 '{clip_layer}' 不存在"}

    results = []
    errors = []
    skipped = []

    for layer_name in layer_names:
        layer = _find_layer(layer_name)
        if layer is None:
            skipped.append(f"{layer_name} (图层不存在)")
            continue

        if layer_name == clip_layer:
            skipped.append(f"{layer_name} (不能裁剪自身)")
            continue

        feature_count_before = layer.featureCount() if hasattr(layer, 'featureCount') else 0

        try:
            params = {
                "INPUT": layer,
                "OVERLAY": boundary,
                "OUTPUT": "memory:",
            }

            result = processing.run("native:clip", params)

            if result and "OUTPUT" in result:
                output_layer = result["OUTPUT"]
                output_layer.setName(f"{layer_name}_clipped")
                project.addMapLayer(output_layer)

                feature_count_after = output_layer.featureCount()
                results.append({
                    "input": layer_name,
                    "output": output_layer.name(),
                    "features_before": feature_count_before,
                    "features_after": feature_count_after,
                })
            else:
                errors.append(f"{layer_name}: Processing 返回空结果")

        except Exception as e:
            logger.exception(f"Clip error for layer '{layer_name}'")
            errors.append(f"{layer_name}: {str(e)}")

    success = len(results) > 0
    msg_parts = []
    if results:
        msg_parts.append(f"成功裁剪 {len(results)} 个图层")
    if skipped:
        msg_parts.append(f"跳过 {len(skipped)} 个: {', '.join(skipped)}")
    if errors:
        msg_parts.append(f"失败 {len(errors)} 个: {'; '.join(errors)}")

    return {
        "success": success,
        "message": "，".join(msg_parts),
        "results": results,
        "errors": errors,
        "skipped": skipped,
    }


def _find_layer(name: str):
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None
