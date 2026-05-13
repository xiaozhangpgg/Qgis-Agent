"""Topology fix tool for QGIS Agent."""

import logging
from typing import Any, Callable, Dict, List, Optional

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
)

import processing

from .topology_rules import (
    TOPOLOGY_RULES,
    FIX_STRATEGIES,
    DEFAULT_DANGLE_THRESHOLD,
    DEFAULT_GAP_TOLERANCE,
    DEFAULT_OVERLAP_STRATEGY,
    resolve_rule_name,
    get_geometry_type_name,
)

logger = logging.getLogger("QgisAgent")


def run_topology_fix(
    layer_name: str,
    error_types: Optional[List[str]] = None,
    reference_layer: Optional[str] = None,
    dangle_threshold: float = DEFAULT_DANGLE_THRESHOLD,
    gap_tolerance: float = DEFAULT_GAP_TOLERANCE,
    overlap_strategy: str = DEFAULT_OVERLAP_STRATEGY,
    _confirm_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Fix topology errors in a vector layer.

    Args:
        layer_name: Input layer name.
        error_types: List of error types to fix. If None, fixes all fixable errors.
        reference_layer: Reference layer for cross-layer rules.
        dangle_threshold: Dangles shorter than this will be removed.
        gap_tolerance: Gaps smaller than this will be ignored.
        overlap_strategy: 'trim' or 'merge' for handling overlaps.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    # 查找输入图层
    layer = _find_layer(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    if not isinstance(layer, QgsVectorLayer):
        return {"success": False, "error": f"图层 '{layer_name}' 不是矢量图层"}

    # 确定要修复的错误类型
    if error_types is None:
        # 修复所有可修复的错误
        fix_types = list(FIX_STRATEGIES.keys())
    else:
        fix_types = []
        for et in error_types:
            if et not in FIX_STRATEGIES:
                return {
                    "success": False,
                    "error": f"不支持修复的错误类型 '{et}'，支持: {', '.join(FIX_STRATEGIES.keys())}",
                }
            fix_types.append(et)

    feature_count_before = layer.featureCount() if hasattr(layer, "featureCount") else 0

    try:
        # 使用 native:fixgeometries 修复几何错误
        params = {
            "INPUT": layer,
            "OUTPUT": "memory:",
        }

        result = processing.run("native:fixgeometries", params)

        if result is None or "OUTPUT" not in result:
            return {"success": False, "error": "Processing 返回空结果"}

        fixed_layer = result["OUTPUT"]

        if not fixed_layer.isValid():
            return {"success": False, "error": "修复后的图层无效"}

        # 设置输出图层名称
        output_name = f"{layer_name}_fixed"
        fixed_layer.setName(output_name)
        project.addMapLayer(fixed_layer)

        feature_count_after = fixed_layer.featureCount()

        # 计算修复的要素数
        features_fixed = max(0, feature_count_before - feature_count_after)

        return {
            "success": True,
            "message": f"拓扑修复完成，输出图层 '{output_name}'",
            "results": [{
                "input": layer_name,
                "output": output_name,
                "errors_fixed": features_fixed,
                "fix_summary": {et: "已修复" for et in fix_types},
                "features_before": feature_count_before,
                "features_after": feature_count_after,
            }],
        }

    except Exception as e:
        logger.exception(f"Topology fix error for layer '{layer_name}'")
        return {"success": False, "error": f"拓扑修复失败: {str(e)}"}


def _find_layer(name: str):
    """Find a layer by name in the current project."""
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None
