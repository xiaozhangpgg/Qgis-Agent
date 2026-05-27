import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")


def run_multipart_to_singleparts(
    layer_name: str,
    output_name: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """将多部件要素图层拆分为单部件要素。

    Args:
        layer_name: 输入图层名称。
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

    input_count = max(layer.featureCount(), 0)

    try:
        result = processing.run("native:multiparttosingleparts", {
            "INPUT": layer,
            "OUTPUT": "memory:",
        })

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            out_name = resolve_output_name(
                project, output_name or f"{layer_name}_singleparts"
            )
            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            count = output_layer.featureCount()

            return {
                "success": True,
                "message": f"将 '{layer_name}' 拆分为 {count} 个单部件要素（原 {input_count} 个）",
                "results": [{
                    "input": layer_name,
                    "output": out_name,
                    "features_before": input_count,
                    "features_after": count,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"多部件转单部件失败，图层 '{layer_name}'")
        return {"success": False, "error": f"多部件转单部件失败: {str(e)}"}
