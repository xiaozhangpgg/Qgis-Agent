import logging
from typing import Any, Callable, Dict, List, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")


def run_merge_vector_layers(
    layer_names: List[str],
    output_name: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """合并多个矢量图层。

    Args:
        layer_names: 要合并的图层名称列表。
        output_name: 可选的输出图层名称。

    Returns:
        包含 success、message、results 的字典。
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    if len(layer_names) == 0:
        return {"success": False, "error": "图层列表不能为空"}

    layers = []
    for name in layer_names:
        layer = find_layer(name)
        if layer is None:
            return {"success": False, "error": f"图层 '{name}' 不存在"}
        if not isinstance(layer, QgsVectorLayer):
            return {"success": False, "error": f"图层 '{name}' 不是矢量图层"}
        layers.append(layer)

    crs_mismatch = False
    crs_list = []
    for i in range(1, len(layers)):
        if layers[i].crs() != layers[0].crs():
            crs_mismatch = True
            crs_list.append(
                f"'{layer_names[0]}' ({layers[0].crs().authid()}) vs "
                f"'{layer_names[i]}' ({layers[i].crs().authid()})"
            )

    try:
        params = {
            "LAYERS": layers,
            "CRS": layers[0].crs(),
            "OUTPUT": "memory:",
        }

        result = processing.run("native:mergevectorlayers", params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            count = output_layer.featureCount()

            out_name = resolve_output_name(
                project, output_name or f"merge_{len(layer_names)}layers"
            )
            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            message = f"合并 {len(layer_names)} 个图层完成，共 {count} 个要素"
            if crs_mismatch:
                message += (
                    "。注意：部分图层坐标系不一致: "
                    + "; ".join(crs_list)
                    + "，合并时已统一为第一个图层的坐标系"
                )

            return {
                "success": True,
                "message": message,
                "results": [{
                    "inputs": layer_names,
                    "output": out_name,
                    "features_output": count,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Merge vector layers error for layers '{layer_names}'")
        return {"success": False, "error": f"合并图层失败: {str(e)}"}
