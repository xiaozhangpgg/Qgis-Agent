import logging
import os
import re
import tempfile
import uuid
from typing import Any, Callable, Dict, List, Optional

from qgis.core import QgsProject, QgsRasterLayer

import processing

from ._utils import find_layer

logger = logging.getLogger("QgisAgent")


def run_raster_calculator(
    expression: str,
    input_rasters: List[str],
    output_name: Optional[str] = None,
    cellsize: Optional[float] = None,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Execute raster calculator with given expression.

    Args:
        expression: Raster calculator expression, e.g. '"raster_a@1" * 2 + "raster_b@1"'.
                    Band references use the raster name from input_rasters list.
        input_rasters: List of input raster layer names.
        output_name: Optional output layer name.
        cellsize: Optional output cell size. Defaults to the first input raster's cell size.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    if not expression or not expression.strip():
        return {"success": False, "error": "计算表达式不能为空"}

    if not input_rasters:
        return {"success": False, "error": "至少需要一个输入栅格图层"}

    layers = {}
    for name in input_rasters:
        layer = find_layer(name)
        if layer is None:
            return {"success": False, "error": f"栅格图层 '{name}' 不存在"}
        layers[name] = layer

    referenced = _extract_referenced_layers(expression)
    for ref_name in referenced:
        if ref_name not in layers:
            return {
                "success": False,
                "error": f"表达式中引用了图层 '{ref_name}'，但未在 input_rasters 中提供",
            }

    try:
        output_path = os.path.join(tempfile.gettempdir(), f"qgisagent_raster_{uuid.uuid4().hex[:8]}.tif")

        params = {
            "EXPRESSION": expression,
            "LAYERS": list(layers.values()),
            "OUTPUT": output_path,
        }
        if cellsize is not None and cellsize > 0:
            params["CELLSIZE"] = cellsize

        result = processing.run("native:rastercalc", params)

        if result and "OUTPUT" in result:
            output_path = result["OUTPUT"]

            out_name = output_name or f"raster_calc_result"
            output_layer = QgsRasterLayer(output_path, out_name)

            if output_layer.isValid():
                project.addMapLayer(output_layer)
                return {
                    "success": True,
                    "message": f"栅格计算完成，结果图层: '{out_name}'",
                    "results": [{
                        "input_rasters": input_rasters,
                        "expression": expression,
                        "output": out_name,
                    }],
                }
            else:
                _cleanup_file(output_path)
                return {"success": False, "error": "输出栅格图层无效"}
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Raster calculator error")
        return {"success": False, "error": f"栅格计算失败: {str(e)}"}


def _extract_referenced_layers(expression: str) -> List[str]:
    return re.findall(r'"([^"]+)@\d+"', expression)


def _cleanup_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.warning(f"Failed to cleanup temp file: {path}")

