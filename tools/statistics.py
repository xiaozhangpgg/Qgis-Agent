import logging
from typing import Any, Callable, Dict, List, Optional

from qgis.core import QgsProject

import processing

logger = logging.getLogger("QgisAgent")


def run_statistics(
    layer_name: str,
    value_field: str,
    category_field: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Compute statistics for a field, optionally grouped by categories.

    Args:
        layer_name: Input layer name.
        value_field: Field to compute statistics on (numeric).
        category_field: Optional field to group by. If None, computes overall statistics.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    layer = _find_layer(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    # Validate fields exist
    fields = [f.name() for f in layer.fields()]
    if value_field not in fields:
        return {"success": False, "error": f"字段 '{value_field}' 不存在于图层 '{layer_name}' 中，可用字段: {', '.join(fields)}"}

    if category_field and category_field not in fields:
        return {"success": False, "error": f"分类字段 '{category_field}' 不存在于图层 '{layer_name}' 中，可用字段: {', '.join(fields)}"}

    try:
        if category_field:
            params = {
                "INPUT": layer,
                "VALUES_FIELD_NAME": value_field,
                "CATEGORIES_FIELD_NAME": [category_field],
                "OUTPUT": "memory:",
            }

            result = processing.run("qgis:statisticsbycategories", params)

            if result and "OUTPUT" in result:
                output_layer = result["OUTPUT"]
                output_layer.setName(f"{layer_name}_stats_{value_field}_by_{category_field}")
                project.addMapLayer(output_layer)

                feature_count = output_layer.featureCount()
                return {
                    "success": True,
                    "message": (
                        f"统计完成：按 '{category_field}' 分组，对 '{value_field}' 进行统计，"
                        f"共 {feature_count} 个分组"
                    ),
                    "results": [{
                        "input": layer_name,
                        "value_field": value_field,
                        "category_field": category_field,
                        "output": output_layer.name(),
                        "group_count": feature_count,
                    }],
                }
            else:
                return {"success": False, "error": "Processing 返回空结果"}
        else:
            # Use qgis:basicstatisticsforfields for overall stats (no categories)
            params = {
                "INPUT": layer,
                "FIELD": value_field,
            }

            result = processing.run("qgis:basicstatisticsforfields", params)

            if result:
                stats = {
                    "count": result.get("COUNT", 0),
                    "unique": result.get("UNIQUE", 0),
                    "min": result.get("MIN", None),
                    "max": result.get("MAX", None),
                    "range": result.get("RANGE", None),
                    "sum": result.get("SUM", None),
                    "mean": result.get("MEAN", None),
                    "median": result.get("MEDIAN", None),
                    "stddev": result.get("STD_DEV", None),
                }
                return {
                    "success": True,
                    "message": f"统计完成：对 '{value_field}' 进行了整体统计",
                    "results": [{
                        "input": layer_name,
                        "value_field": value_field,
                        "statistics": stats,
                    }],
                }
            else:
                return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Statistics error for layer '{layer_name}'")
        return {"success": False, "error": f"统计汇总失败: {str(e)}"}


def _find_layer(name: str):
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None
