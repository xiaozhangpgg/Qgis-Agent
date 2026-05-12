import logging
import os
from typing import Any, Callable, Dict, List, Optional

from qgis.core import QgsProject

import processing

logger = logging.getLogger("QgisAgent")

FORMAT_EXTENSIONS = {
    "geojson": "geojson",
    "gpkg": "gpkg",
    "kml": "kml",
    "csv": "csv",
    "shp": "shp",
    "gml": "gml",
}


def run_batch_export(
    layer_names: List[str],
    output_format: str,
    output_dir: str,
    _confirm_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Batch export multiple layers to files in the specified format.

    Args:
        layer_names: List of layer names to export.
        output_format: Target format: geojson, gpkg, kml, csv, shp, gml.
        output_dir: Output directory path.

    Returns:
        Dict with 'success', 'message', 'results', 'errors', 'skipped' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    fmt = output_format.lower().strip().lstrip(".")
    if fmt not in FORMAT_EXTENSIONS:
        return {
            "success": False,
            "error": f"不支持的输出格式 '{output_format}'，可选: {', '.join(FORMAT_EXTENSIONS.keys())}",
        }

    if not output_dir:
        return {"success": False, "error": "必须指定输出目录"}

    os.makedirs(output_dir, exist_ok=True)
    ext = FORMAT_EXTENSIONS[fmt]

    results = []
    errors = []
    skipped = []

    for layer_name in layer_names:
        layer = _find_layer(layer_name)
        if layer is None:
            skipped.append(f"{layer_name} (图层不存在)")
            continue

        feature_count = layer.featureCount() if hasattr(layer, "featureCount") else 0

        try:
            output_path = os.path.join(output_dir, f"{layer_name}.{ext}")

            # Check overwrite
            if os.path.exists(output_path) and _confirm_callback:
                result = _confirm_callback(f"文件 '{output_path}' 已存在，是否覆盖？")
                if not result.confirmed:
                    skipped.append(f"{layer_name} (用户取消覆盖)")
                    continue

            params = {
                "INPUT": layer,
                "OUTPUT": output_path,
            }

            result = processing.run("native:savefeatures", params)

            if result and "OUTPUT" in result:
                results.append({
                    "input": layer_name,
                    "output_path": result["OUTPUT"],
                    "format": fmt,
                    "feature_count": feature_count,
                })
            else:
                errors.append(f"{layer_name}: Processing 返回空结果")

        except Exception as e:
            logger.exception(f"Export error for layer '{layer_name}'")
            errors.append(f"{layer_name}: {str(e)}")

    success = len(results) > 0
    msg_parts = []
    if results:
        msg_parts.append(f"成功导出 {len(results)} 个图层到 {output_dir}")
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
