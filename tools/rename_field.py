import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import QgsProject, QgsVectorLayer

import processing

from ._utils import find_layer, resolve_output_name

logger = logging.getLogger("QgisAgent")


def run_rename_field(
    layer_name: str,
    old_name: str,
    new_name: str,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """重命名矢量图层中的字段。

    Args:
        layer_name: 输入图层名称。
        old_name: 原字段名称。
        new_name: 新字段名称。

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
    if old_name not in existing_fields:
        return {"success": False, "error": f"图层 '{layer_name}' 中不存在字段 '{old_name}'"}
    if not new_name or not new_name.strip():
        return {"success": False, "error": "新字段名不能为空"}
    if old_name == new_name:
        return {"success": False, "error": "新旧字段名相同，无需重命名"}
    if new_name in existing_fields:
        return {"success": False, "error": f"字段名 '{new_name}' 已存在，请使用其他名称"}

    try:
        result = processing.run("native:renametablefield", {
            "INPUT": layer,
            "FIELD": old_name,
            "NEW_NAME": new_name,
            "OUTPUT": "memory:",
        })

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]
            out_name = resolve_output_name(project, f"{layer_name}_renamed")
            output_layer.setName(out_name)
            project.addMapLayer(output_layer)

            return {
                "success": True,
                "message": f"在 '{layer_name}' 中将字段 '{old_name}' 重命名为 '{new_name}'",
                "results": [{
                    "input": layer_name,
                    "output": out_name,
                    "old_name": old_name,
                    "new_name": new_name,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"重命名字段失败，图层 '{layer_name}'")
        return {"success": False, "error": f"重命名字段失败: {str(e)}"}
