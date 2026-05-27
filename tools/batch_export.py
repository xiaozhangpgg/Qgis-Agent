import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer_case_insensitive, FORMAT_EXTENSIONS

logger = logging.getLogger("QgisAgent")

_ILLEGAL_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')


def run_batch_export(
    layer_names: List[str],
    output_format: str,
    output_dir: str,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
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

    if not callable(getattr(processing, "run", None)):
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
        layer = find_layer_case_insensitive(layer_name)
        if layer is None:
            skipped.append(f"{layer_name} (图层不存在)")
            continue

        if not isinstance(layer, QgsVectorLayer):
            skipped.append(f"{layer_name} (非矢量图层，无法导出)")
            continue

        feature_count = layer.featureCount() if hasattr(layer, "featureCount") else 0

        try:
            safe_name = _ILLEGAL_FILENAME_RE.sub("_", layer_name)
            output_path = os.path.join(output_dir, f"{safe_name}.{ext}")

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

    total = len(layer_names)
    if len(results) == total:
        success = True
        status = "all_success"
    elif len(results) > 0:
        success = True
        status = "partial_success"
    else:
        success = False
        status = "all_failed"
    msg_parts = []
    if results:
        msg_parts.append(f"成功导出 {len(results)} 个图层到 {output_dir}")
    if skipped:
        msg_parts.append(f"跳过 {len(skipped)} 个: {', '.join(skipped)}")
    if errors:
        msg_parts.append(f"失败 {len(errors)} 个: {'; '.join(errors)}")

    return {
        "success": success,
        "status": status,
        "message": "，".join(msg_parts),
        "results": results,
        "errors": errors,
        "skipped": skipped,
    }

