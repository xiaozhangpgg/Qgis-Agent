"""Topology rules mapping and constants."""

from typing import Dict, Tuple, Optional

# 规则名映射: 简化名 → (QGIS算法ID, 错误类型, 规则描述, 适用图层类型)
TOPOLOGY_RULES: Dict[str, Tuple[str, str, str, str]] = {
    # 面规则
    "no_overlaps": ("native:checkvalidity", "overlap", "面要素不能重叠", "polygon"),
    "no_gaps": ("native:checkvalidity", "gap", "面要素不能有缝隙", "polygon"),
    "polygon_coverage": ("native:checkvalidity", "polygon_not_covered", "面必须被覆盖", "polygon"),

    # 线规则
    "no_dangles": ("native:checkvalidity", "dangle", "线要素不能有悬挂节点", "line"),
    "no_self_intersections": ("native:checkvalidity", "self_intersection", "要素不能自相交", "all"),
    "no_pseudo_nodes": ("native:checkvalidity", "pseudo_node", "线要素不能有伪节点", "line"),

    # 点规则
    "no_duplicate_points": ("native:checkvalidity", "duplicate_point", "点要素不能重叠", "point"),

    # 跨图层规则
    "point_in_polygon": ("native:checkvalidity", "point_outside_polygon", "点必须在面内", "point"),
    "line_in_polygon": ("native:checkvalidity", "line_outside_polygon", "线必须在面内", "line"),

    # 通用规则
    "invalid_geometry": ("native:checkvalidity", "invalid_geometry", "几何必须有效", "all"),
}

# QGIS 原生规则名到简化名的反向映射
QGIS_RULE_ALIASES: Dict[str, str] = {
    "QgsGeometryValidate.NoOverlaps": "no_overlaps",
    "QgsGeometryValidate.NoGaps": "no_gaps",
    "QgsGeometryValidate.NoDangles": "no_dangles",
    "QgsGeometryValidate.NoSelfIntersections": "no_self_intersections",
}

# 默认参数
DEFAULT_DANGLE_THRESHOLD = 0.001
DEFAULT_GAP_TOLERANCE = 0.0001
DEFAULT_OVERLAP_STRATEGY = "trim"

# 修复算法映射: 错误类型 → 修复策略
FIX_STRATEGIES: Dict[str, str] = {
    "overlap": "difference",
    "gap": "buffer_dissolve",
    "dangle": "extract_delete",
    "self_intersection": "fix_geometries",
    "duplicate_point": "remove_duplicates",
    "invalid_geometry": "fix_geometries",
    "pseudo_node": "extract_delete",
}


def resolve_rule_name(rule: str) -> Optional[str]:
    """Resolve a rule name (simplified or QGIS native) to simplified form.

    Args:
        rule: Rule name in either simplified or QGIS native format.

    Returns:
        Simplified rule name, or None if not found.
    """
    # 先检查是否是简化名
    if rule in TOPOLOGY_RULES:
        return rule

    # 再检查是否是 QGIS 原生规则名
    return QGIS_RULE_ALIASES.get(rule)


def get_rules_for_geometry_type(geometry_type: str) -> list:
    """Get all applicable rules for a geometry type.

    Args:
        geometry_type: 'point', 'line', or 'polygon'.

    Returns:
        List of applicable rule names.
    """
    applicable = []
    for rule_name, (_, _, _, applicable_type) in TOPOLOGY_RULES.items():
        if applicable_type == "all" or applicable_type == geometry_type:
            applicable.append(rule_name)
    return applicable


def get_geometry_type_name(layer) -> str:
    """Get geometry type name from a QGIS layer.

    Args:
        layer: QgsVectorLayer instance.

    Returns:
        'point', 'line', or 'polygon'.
    """
    from qgis.core import QgsWkbTypes

    geom_type = layer.geometryType()
    if geom_type == QgsWkbTypes.PointGeometry:
        return "point"
    elif geom_type == QgsWkbTypes.LineGeometry:
        return "line"
    elif geom_type == QgsWkbTypes.PolygonGeometry:
        return "polygon"
    return "unknown"
