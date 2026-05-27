import logging
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from qgis.core import (
    QgsProject,
    QgsWkbTypes,
)

import processing

from ._utils import find_layer_with_warnings, resolve_input

logger = logging.getLogger("QgisAgent")


def run_batch_clip(
    layer_names: List[str],
    clip_layer: str,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
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

    boundary, boundary_warnings = find_layer_with_warnings(clip_layer)
    if boundary is None:
        return {"success": False, "error": f"裁剪边界图层 '{clip_layer}' 不存在"}

    if not boundary.isValid():
        return {"success": False, "error": f"裁剪边界图层 '{clip_layer}' 无效，数据源可能已损坏"}

    if boundary.geometryType() != QgsWkbTypes.PolygonGeometry:
        return {"success": False, "error": f"裁剪边界图层 '{clip_layer}' 必须是面图层"}

    if boundary.featureCount() == 0:
        return {"success": False, "error": f"裁剪边界图层 '{clip_layer}' 无要素，无法执行裁剪"}

    boundary_crs = boundary.crs()

    results = []
    errors = []
    skipped = []
    warnings = list(boundary_warnings)

    for layer_name in layer_names:
        layer, layer_warnings = find_layer_with_warnings(layer_name)
        warnings.extend(layer_warnings)

        if layer is None:
            skipped.append(f"{layer_name} (图层不存在)")
            continue

        if not layer.isValid():
            skipped.append(f"{layer_name} (图层无效，数据源可能已损坏)")
            continue

        if layer_name == clip_layer:
            skipped.append(f"{layer_name} (不能裁剪自身)")
            continue

        if layer.crs() != boundary_crs:
            skipped.append(
                f"{layer_name} (CRS 不一致: {layer.crs().authid()} vs {boundary_crs.authid()})"
            )
            continue

        raw_count = layer.featureCount()
        feature_count_before = raw_count if raw_count >= 0 else None

        try:
            input_value = resolve_input(layer)
            overlay_value = resolve_input(boundary)

            params = {
                "INPUT": input_value,
                "OVERLAY": overlay_value,
                "OUTPUT": "memory:",
            }

            result = processing.run("native:clip", params)

            if result and "OUTPUT" in result:
                output_layer = result["OUTPUT"]
                output_name = f"{layer_name}_clipped"
                output_layer.setName(output_name)
                project.addMapLayer(output_layer)

                output_layer.updateExtents()
                raw_after = output_layer.featureCount()
                feature_count_after = raw_after if raw_after >= 0 else None
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
        "warnings": warnings,
    }


