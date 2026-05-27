import logging
from typing import Any, Callable, Dict, List, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")


def run_delete_fields(
    layer_name: str,
    field_names: List[str],
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """从矢量图层中删除指定字段。

    Args:
        layer_name: 输入图层名称。
        field_names: 要删除的字段名称列表。

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

    # 字段校验
    existing_fields = {f.name() for f in layer.fields()}
    missing = [f for f in field_names if f not in existing_fields]
    if missing:
        return {"success": False, "error": f"图层 '{layer_name}' 中不存在字段: {', '.join(missing)}"}

    unique_fields = list(dict.fromkeys(field_names))  # 去重保序
    if len(existing_fields) - len(unique_fields) < 1:
        return {"success": False, "error": "至少需要保留一个字段，不能删除全部字段"}

    try:
        result = processing.run("native:deletecolumn", {
            "INPUT": layer,
            "COLUMN": unique_fields,
            "OUTPUT": "memory:",
        })

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            out_name = resolve_output_name(project, f"{layer_name}_del_fields")
            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            return {
                "success": True,
                "message": f"从 '{layer_name}' 中删除了 {len(unique_fields)} 个字段: {', '.join(unique_fields)}",
                "results": [{
                    "input": layer_name,
                    "output": out_name,
                    "deleted_fields": unique_fields,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"删除字段失败，图层 '{layer_name}'")
        return {"success": False, "error": f"删除字段失败: {str(e)}"}
