import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")


def run_symmetrical_difference(
    layer_a: str,
    layer_b: str,
    output_name: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """对两个矢量图层执行对称差异分析。

    Args:
        layer_a: 第一个（输入）图层名称。
        layer_b: 第二个（叠加）图层名称。
        output_name: 可选的输出图层名称。

    Returns:
        包含 'success'、'message'、'results' 键的字典。
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    input_layer = find_layer(layer_a)
    if input_layer is None:
        return {"success": False, "error": f"图层 '{layer_a}' 不存在"}

    overlay_layer = find_layer(layer_b)
    if overlay_layer is None:
        return {"success": False, "error": f"图层 '{layer_b}' 不存在"}

    if not isinstance(input_layer, QgsVectorLayer):
        return {"success": False, "error": f"图层 '{layer_a}' 不是矢量图层"}

    if not isinstance(overlay_layer, QgsVectorLayer):
        return {"success": False, "error": f"图层 '{layer_b}' 不是矢量图层"}

    if layer_a == layer_b:
        return {"success": False, "error": "对称差异分析不能对同一图层执行"}

    if input_layer.crs() != overlay_layer.crs():
        return {
            "success": False,
            "error": (
                f"图层 CRS 不一致: '{layer_a}' 为 {input_layer.crs().authid()}, "
                f"'{layer_b}' 为 {overlay_layer.crs().authid()}"
            ),
        }

    try:
        result = processing.run("native:symmetricaldifference", {
            "INPUT": input_layer,
            "OVERLAY": overlay_layer,
            "OUTPUT": "memory:",
        })

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            out_name = resolve_output_name(
                project, output_name or f"{layer_a}_symdiff_{layer_b}"
            )
            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            count = output_layer.featureCount()

            return {
                "success": True,
                "message": f"对称差异分析完成，'{layer_a}' 与 '{layer_b}' 处理后得到 {count} 个要素",
                "results": [{
                    "input_a": layer_a,
                    "input_b": layer_b,
                    "output": out_name,
                    "features_output": count,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"对称差异分析失败: '{layer_a}' 与 '{layer_b}'")
        return {"success": False, "error": f"对称差异分析失败: {str(e)}"}
