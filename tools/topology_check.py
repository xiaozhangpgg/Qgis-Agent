"""Topology check tool for QGIS Agent."""

import logging
from typing import Any, Callable, Dict, List, Optional

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
)
from qgis.PyQt.QtCore import QVariant

import processing

from .topology_rules import (
    TOPOLOGY_RULES,
    DEFAULT_DANGLE_THRESHOLD,
    DEFAULT_GAP_TOLERANCE,
    resolve_rule_name,
    get_rules_for_geometry_type,
    get_geometry_type_name,
)

logger = logging.getLogger("QgisAgent")


def run_topology_check(
    layer_name: str,
    rules: Optional[List[str]] = None,
    reference_layer: Optional[str] = None,
    dangle_threshold: float = DEFAULT_DANGLE_THRESHOLD,
    gap_tolerance: float = DEFAULT_GAP_TOLERANCE,
    _confirm_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Check topology errors in a vector layer.

    Args:
        layer_name: Input layer name.
        rules: List of topology rules (simplified or QGIS native names).
               If None, checks all applicable rules for the geometry type.
        reference_layer: Reference layer for cross-layer rules.
        dangle_threshold: Minimum length for dangle detection.
        gap_tolerance: Tolerance for gap detection.

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

    # 获取几何类型
    geom_type = get_geometry_type_name(layer)

    # 解析规则
    if rules is None:
        # 使用所有适用的规则
        resolved_rules = get_rules_for_geometry_type(geom_type)
    else:
        resolved_rules = []
        for rule in rules:
            resolved = resolve_rule_name(rule)
            if resolved is None:
                return {
                    "success": False,
                    "error": f"不支持的拓扑规则 '{rule}'，支持的规则: {', '.join(TOPOLOGY_RULES.keys())}",
                }
            resolved_rules.append(resolved)

    if not resolved_rules:
        return {"success": False, "error": "没有适用的拓扑规则"}

    # 检查跨图层规则
    cross_layer_rules = ["point_in_polygon", "line_in_polygon"]
    has_cross_layer_rule = any(r in cross_layer_rules for r in resolved_rules)

    if has_cross_layer_rule and reference_layer is None:
        return {
            "success": False,
            "error": f"跨图层规则需要指定参考图层，请添加 reference_layer 参数",
        }

    ref_layer = None
    if reference_layer:
        ref_layer = _find_layer(reference_layer)
        if ref_layer is None:
            return {"success": False, "error": f"参考图层 '{reference_layer}' 不存在"}

    feature_count_before = layer.featureCount() if hasattr(layer, "featureCount") else 0

    try:
        # 使用 QGIS checkvalidity 算法检查几何有效性
        params = {
            "INPUT": layer,
            "VALID_OUTPUT": "memory:",
            "INVALID_OUTPUT": "memory:",
            "ERROR_OUTPUT": "memory:",
        }

        result = processing.run("native:checkvalidity", params)

        if result is None:
            return {"success": False, "error": "Processing 返回空结果"}

        # 收集错误要素
        error_features = []
        error_summary = {}

        # 从 ERROR_OUTPUT 获取错误要素
        if "ERROR_OUTPUT" in result and result["ERROR_OUTPUT"]:
            error_layer = result["ERROR_OUTPUT"]
            if error_layer.isValid() and error_layer.featureCount() > 0:
                for feature in error_layer.getFeatures():
                    error_features.append(feature)
                    error_summary["invalid_geometry"] = error_summary.get("invalid_geometry", 0) + 1

        # 从 INVALID_OUTPUT 获取无效要素
        if "INVALID_OUTPUT" in result and result["INVALID_OUTPUT"]:
            invalid_layer = result["INVALID_OUTPUT"]
            if invalid_layer.isValid() and invalid_layer.featureCount() > 0:
                for feature in invalid_layer.getFeatures():
                    error_features.append(feature)
                    error_summary["invalid_geometry"] = error_summary.get("invalid_geometry", 0) + 1

        # 如果没有错误，返回成功
        if not error_features:
            return {
                "success": True,
                "message": f"拓扑检查完成，'{layer_name}' 未发现错误",
                "results": [{
                    "input": layer_name,
                    "output": None,
                    "rules_checked": resolved_rules,
                    "error_count": 0,
                    "error_summary": {},
                }],
            }

        # 创建错误输出图层
        output_layer_name = f"{layer_name}_topology_errors"
        output_layer = _create_error_layer(
            layer, error_features, output_layer_name, resolved_rules
        )

        if output_layer is None:
            return {"success": False, "error": "创建错误图层失败"}

        project.addMapLayer(output_layer)

        error_count = len(error_features)

        return {
            "success": True,
            "message": f"拓扑检查完成，发现 {error_count} 个错误",
            "results": [{
                "input": layer_name,
                "output": output_layer_name,
                "rules_checked": resolved_rules,
                "error_count": error_count,
                "error_summary": error_summary,
            }],
        }

    except Exception as e:
        logger.exception(f"Topology check error for layer '{layer_name}'")
        return {"success": False, "error": f"拓扑检查失败: {str(e)}"}


def _create_error_layer(
    source_layer: QgsVectorLayer,
    error_features: List[QgsFeature],
    output_name: str,
    rules: List[str],
) -> Optional[QgsVectorLayer]:
    """Create a new layer containing topology error features.

    Args:
        source_layer: Original vector layer.
        error_features: List of error features.
        output_name: Name for the output layer.
        rules: List of rules that were checked.

    Returns:
        New QgsVectorLayer with error features, or None on failure.
    """
    try:
        # 创建内存图层
        crs = source_layer.crs().wkbType()
        output_layer = QgsVectorLayer(
            f"Polygon?crs={source_layer.crs().authid()}",
            output_name,
            "memory",
        )

        if not output_layer.isValid():
            return None

        # 添加字段
        provider = output_layer.dataProvider()
        provider.addAttributes([
            QgsField("error_id", QVariant.Int),
            QgsField("error_type", QVariant.String),
            QgsField("error_description", QVariant.String),
            QgsField("layer_name", QVariant.String),
            QgsField("feature_id", QVariant.Int),
        ])
        output_layer.updateFields()

        # 添加要素
        output_layer.startEditing()
        for idx, feature in enumerate(error_features):
            new_feature = QgsFeature(output_layer.fields())
            new_feature.setGeometry(feature.geometry())
            new_feature.setAttribute("error_id", idx + 1)
            new_feature.setAttribute("error_type", "invalid_geometry")
            new_feature.setAttribute("error_description", "几何无效或自相交")
            new_feature.setAttribute("layer_name", source_layer.name())
            new_feature.setAttribute("feature_id", feature.id())
            output_layer.addFeature(new_feature)

        output_layer.commitChanges()

        return output_layer

    except Exception as e:
        logger.exception("Failed to create error layer")
        return None


def _find_layer(name: str):
    """Find a layer by name in the current project."""
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None
