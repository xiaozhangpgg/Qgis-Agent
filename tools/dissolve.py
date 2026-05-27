import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")


def run_dissolve(
    layer_name: str,
    dissolve_field: Optional[str] = None,
    output_name: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """对矢量图层执行溶解操作。

    Args:
        layer_name: 输入图层名称。
        dissolve_field: 可选的溶解字段，为空时全部要素合并为一个。
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

    if dissolve_field is not None:
        if layer.fields().indexFromName(dissolve_field) == -1:
            return {
                "success": False,
                "error": f"图层 '{layer_name}' 中不存在字段 '{dissolve_field}'",
            }

    try:
        params = {
            "INPUT": layer,
            "FIELD": dissolve_field if dissolve_field else "",
            "OUTPUT": "memory:",
        }

        result = processing.run("native:dissolve", params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            count = output_layer.featureCount()

            if output_name:
                out_name = output_name
            elif dissolve_field:
                out_name = resolve_output_name(
                    project, f"{layer_name}_dissolve_{dissolve_field}"
                )
            else:
                out_name = resolve_output_name(project, f"{layer_name}_dissolve")

            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            if dissolve_field:
                message = f"对 '{layer_name}' 按字段 '{dissolve_field}' 溶解完成，生成 {count} 个要素"
            else:
                message = f"对 '{layer_name}' 全部溶解完成，生成 {count} 个要素"

            return {
                "success": True,
                "message": message,
                "results": [{
                    "input": layer_name,
                    "output": out_name,
                    "dissolve_field": dissolve_field or "(全部)",
                    "features_output": count,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Dissolve error for layer '{layer_name}'")
        return {"success": False, "error": f"溶解操作失败: {str(e)}"}
