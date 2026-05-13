import logging
import os
import tempfile
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer, FORMAT_EXTENSIONS, DRIVER_MAP

logger = logging.getLogger("QgisAgent")


def _sanitize_filename(name: str) -> str:
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name


def run_format_convert(
    layer_name: str,
    output_format: str,
    output_dir: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Convert a vector layer to a different format.

    Args:
        layer_name: Input layer name.
        output_format: Target format: geojson, gpkg, kml, csv, shp, gml.
        output_dir: Optional output directory. If not specified, adds to project.

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

    fmt = output_format.lower().strip().lstrip(".")
    if fmt not in FORMAT_EXTENSIONS:
        return {
            "success": False,
            "error": f"不支持的输出格式 '{output_format}'，可选: {', '.join(FORMAT_EXTENSIONS.keys())}",
        }

    ext = FORMAT_EXTENSIONS[fmt]

    safe_name = _sanitize_filename(layer_name)

    try:
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{safe_name}.{ext}")

            if os.path.exists(output_path) and _confirm_callback:
                result = _confirm_callback(f"文件 '{output_path}' 已存在，是否覆盖？")
                if not result.confirmed:
                    return {"success": False, "error": "用户取消覆盖"}

            params = {
                "INPUT": layer,
                "OUTPUT": output_path,
            }

            result = processing.run("native:savefeatures", params)

            if result and "OUTPUT" in result:
                return {
                    "success": True,
                    "message": f"已将 '{layer_name}' 转换为 {fmt.upper()} 格式，保存到: {result['OUTPUT']}",
                    "results": [{
                        "input": layer_name,
                        "output_format": fmt,
                        "output_path": result["OUTPUT"],
                    }],
                }
            else:
                return {"success": False, "error": "Processing 返回空结果"}
        else:
            tmp_dir = tempfile.mkdtemp()
            tmp_path = os.path.join(tmp_dir, f"{safe_name}.{ext}")

            params = {
                "INPUT": layer,
                "OUTPUT": tmp_path,
            }

            result = processing.run("native:savefeatures", params)

            if result and "OUTPUT" in result:
                output_layer = QgsVectorLayer(tmp_path, f"{layer_name}_{ext}", "ogr")
                if not output_layer.isValid():
                    return {"success": False, "error": f"转换后的图层无效，无法加载"}

                project.addMapLayer(output_layer)

                feature_count = output_layer.featureCount()
                return {
                    "success": True,
                    "message": (
                        f"已将 '{layer_name}' 转换为 {fmt.upper()} 格式，"
                        f"生成 {feature_count} 个要素的图层 '{output_layer.name()}'"
                    ),
                    "results": [{
                        "input": layer_name,
                        "output_format": fmt,
                        "output": output_layer.name(),
                        "feature_count": feature_count,
                    }],
                }
            else:
                return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Format convert error for layer '{layer_name}'")
        return {"success": False, "error": f"格式转换失败: {str(e)}"}

