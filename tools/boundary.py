import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")


def run_boundary(
    layer_name: str,
    output_name: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """提取矢量图层的边界。

    Args:
        layer_name: 输入图层名称。
        output_name: 可选的输出图层名称。

    Returns:
        包含 success、message、results 的字典。
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

    if layer.geometryType() == QgsWkbTypes.PointGeometry:
        return {
            "success": False,
            "error": "边界提取不支持点图层输入",
        }

    try:
        params = {
            "INPUT": layer,
            "OUTPUT": "memory:",
        }

        result = processing.run("native:boundary", params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            count = output_layer.featureCount()

            out_name = resolve_output_name(
                project, output_name or f"{layer_name}_boundary"
            )
            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                message = f"从 '{layer_name}' 提取了 {count} 条边界线"
            else:
                message = f"从 '{layer_name}' 提取了 {count} 个端点"

            return {
                "success": True,
                "message": message,
                "results": [{
                    "input": layer_name,
                    "output": out_name,
                    "features_output": count,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Boundary error for layer '{layer_name}'")
        return {"success": False, "error": f"边界提取失败: {str(e)}"}
