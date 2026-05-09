import logging
import os
from typing import Any, Dict, List, Optional

from qgis.core import (
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsApplication,
)

logger = logging.getLogger("QgisAgent")


def run_batch_reproject(
    layer_names: List[str],
    target_crs: str,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Batch reproject multiple layers to a target CRS.

    Args:
        layer_names: List of layer names to reproject.
        target_crs: Target CRS string, e.g. 'EPSG:4490'.
        output_dir: Optional output directory. If None, layers are added to project.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()
    processing = QgsApplication.processingRegistry()

    if not processing:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    crs = QgsCoordinateReferenceSystem(target_crs)
    if not crs.isValid():
        return {"success": False, "error": f"无效的 CRS: {target_crs}"}

    if output_dir and not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            return {"success": False, "error": f"无法创建输出目录: {e}"}

    results = []
    errors = []
    skipped = []

    for layer_name in layer_names:
        layer = _find_layer(layer_name)
        if layer is None:
            skipped.append(f"{layer_name} (图层不存在)")
            continue

        source_crs = layer.crs()
        if not source_crs.isValid():
            skipped.append(f"{layer_name} (源 CRS 无效)")
            continue

        if source_crs == crs:
            skipped.append(f"{layer_name} (已是目标 CRS)")
            continue

        feature_count_before = layer.featureCount() if hasattr(layer, 'featureCount') else 0

        try:
            params = {
                "INPUT": layer,
                "TARGET_CRS": crs,
                "OUTPUT": "memory:",
            }

            if output_dir:
                ext = ".shp"
                out_path = os.path.join(output_dir, f"{layer_name}_reprojected{ext}")
                if os.path.exists(out_path):
                    os.remove(out_path)
                params["OUTPUT"] = out_path

            result = processing.run("native:reprojectlayer", params)

            if result and "OUTPUT" in result:
                output_layer = result["OUTPUT"]
                if isinstance(output_layer, str):
                    # File output - load it
                    from qgis.core import QgsVectorLayer
                    out_name = f"{layer_name}_{target_crs.split(':')[1]}"
                    output_layer = QgsVectorLayer(output_layer, out_name, "ogr")
                    project.addMapLayer(output_layer)
                else:
                    # Memory layer - rename and add
                    output_layer.setName(f"{layer_name}_{target_crs.split(':')[1]}")
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
            logger.exception(f"Reproject error for layer '{layer_name}'")
            errors.append(f"{layer_name}: {str(e)}")

    success = len(results) > 0
    msg_parts = []
    if results:
        msg_parts.append(f"成功转换 {len(results)} 个图层到 {target_crs}")
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
