import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")


def run_extract_by_extent(
    layer_name: str,
    extent: str,
    output_name: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """按范围提取矢量图层中的要素。

    Args:
        layer_name: 输入图层名称。
        extent: 范围字符串，格式为 'xmin,xmax,ymin,ymax'。
        output_name: 可选的输出图层名称。

    Returns:
        包含 'success'、'message'、'results' 键的字典。
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
        return {"success": False, "error": f"图层 '{layer_name}' 不是矢量图层"}

    # 解析范围
    parts = [p.strip() for p in extent.split(",")]
    if len(parts) != 4:
        return {"success": False, "error": "范围格式错误，应为 'xmin,xmax,ymin,ymax'（4 个逗号分隔的数字）"}
    try:
        xmin, xmax, ymin, ymax = [float(p) for p in parts]
    except ValueError:
        return {"success": False, "error": f"范围坐标包含非数值内容: '{extent}'"}
    if xmin >= xmax or ymin >= ymax:
        return {"success": False, "error": f"范围无效: xmin({xmin}) 必须 < xmax({xmax}), ymin({ymin}) 必须 < ymax({ymax})"}

    try:
        result = processing.run("native:extractbyextent", {
            "INPUT": layer,
            "EXTENT": f"{xmin},{xmax},{ymin},{ymax}",
            "CLIP": False,
            "OUTPUT": "memory:",
        })

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            out_name = resolve_output_name(
                project, output_name or f"{layer_name}_extract"
            )
            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            count = output_layer.featureCount()

            return {
                "success": True,
                "message": f"从 '{layer_name}' 中按范围 [{extent}] 提取了 {count} 个要素",
                "results": [{
                    "input": layer_name,
                    "output": out_name,
                    "extent": extent,
                    "features_output": count,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"按范围提取失败，图层 '{layer_name}'")
        return {"success": False, "error": f"按范围提取失败: {str(e)}"}
