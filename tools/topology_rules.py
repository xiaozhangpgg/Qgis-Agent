"""Topology rules mapping and constants."""

from typing import Dict, List, Optional, Tuple

# 规则名映射: 简化名 → (实现方式, 错误类型, 规则描述, 适用图层类型, 是否跨图层)
# 实现方式: "native:checkvalidity" 仅用于 invalid_geometry，
# 其他规则由 topology_check.py 中的自定义函数实现
TOPOLOGY_RULES: Dict[str, Tuple[str, str, str, str, bool]] = {
    # 面规则
    "no_overlaps": ("custom:spatial_index_intersection", "overlap", "面要素不能重叠", "polygon", False),
    "no_gaps": ("custom:union_hole_detection", "gap", "面要素不能有缝隙", "polygon", False),
    "polygon_coverage": ("custom:union_difference", "polygon_not_covered", "面必须被覆盖", "polygon", True),

    # 线规则
    "no_dangles": ("custom:endpoint_connectivity", "dangle", "线要素不能有悬挂节点", "line", False),
    "no_self_intersections": ("custom:geos_validity", "self_intersection", "要素不能自相交", "all", False),
    "no_pseudo_nodes": ("custom:endpoint_connectivity", "pseudo_node", "线要素不能有伪节点", "line", False),

    # 点规则
    "no_duplicate_points": ("custom:spatial_index_equality", "duplicate_point", "点要素不能重叠", "point", False),

    # 跨图层规则
    "point_in_polygon": ("custom:cross_layer_contains", "point_outside_polygon", "点必须在面内", "point", True),
    "line_in_polygon": ("custom:cross_layer_difference", "line_outside_polygon", "线必须在面内", "line", True),

    # 通用规则
    "invalid_geometry": ("native:checkvalidity", "invalid_geometry", "几何必须有效", "all", False),
}

# QGIS 原生规则名到简化名的反向映射
QGIS_RULE_ALIASES: Dict[str, str] = {
    "QgsGeometryValidate.NoOverlaps": "no_overlaps",
    "QgsGeometryValidate.NoGaps": "no_gaps",
    "QgsGeometryValidate.NoDangles": "no_dangles",
    "QgsGeometryValidate.NoSelfIntersections": "no_self_intersections",
    "QgsGeometryValidate.NoPseudoNodes": "no_pseudo_nodes",
    "QgsGeometryValidate.NoDuplicatePoints": "no_duplicate_points",
    "QgsGeometryValidate.PointInPolygon": "point_in_polygon",
    "QgsGeometryValidate.LineInPolygon": "line_in_polygon",
    "QgsGeometryValidate.PolygonCoverage": "polygon_coverage",
    "QgsGeometryValidate.InvalidGeometry": "invalid_geometry",
}

# 默认参数
DEFAULT_DANGLE_THRESHOLD = 0.001
DEFAULT_GAP_TOLERANCE = 0.0001
DEFAULT_OVERLAP_STRATEGY = "trim"

# 修复算法映射: 错误类型 → 修复策略
FIX_STRATEGIES: Dict[str, str] = {
    "overlap": "difference",
    "gap": "buffer_dissolve",
    "dangle": "extend_to_nearest",
    "self_intersection": "fix_geometries",
    "duplicate_point": "remove_duplicates",
    "invalid_geometry": "fix_geometries",
    "pseudo_node": "merge_lines",
    "polygon_not_covered": "not_auto_fixable",
    "point_outside_polygon": "not_auto_fixable",
    "line_outside_polygon": "not_auto_fixable",
}

# 可自动修复的错误类型
AUTO_FIXABLE_TYPES: List[str] = [
    et for et, strategy in FIX_STRATEGIES.items() if strategy != "not_auto_fixable"
]


def resolve_rule_name(rule: str) -> Optional[str]:
    """Resolve a rule name (simplified or QGIS native) to simplified form.

    Args:
        rule: Rule name in either simplified or QGIS native format.

    Returns:
        Simplified rule name, or None if not found.
    """
    if rule in TOPOLOGY_RULES:
        return rule

    return QGIS_RULE_ALIASES.get(rule)


def is_cross_layer_rule(rule_name: str) -> bool:
    """Check if a rule requires a reference layer.

    Args:
        rule_name: Simplified rule name.

    Returns:
        True if the rule requires a reference layer.
    """
    if rule_name in TOPOLOGY_RULES:
        return TOPOLOGY_RULES[rule_name][4]
    return False


def get_cross_layer_rules() -> List[str]:
    """Get all rules that require a reference layer.

    Returns:
        List of cross-layer rule names.
    """
    return [name for name, (_, _, _, _, cross) in TOPOLOGY_RULES.items() if cross]


def get_rules_for_geometry_type(geometry_type: str) -> list:
    """Get all applicable rules for a geometry type.

    Args:
        geometry_type: 'point', 'line', or 'polygon'.

    Returns:
        List of applicable rule names.
    """
    applicable = []
    for rule_name, (_, _, _, applicable_type, _) in TOPOLOGY_RULES.items():
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


def extract_polygon_parts(geom) -> list:
    from qgis.core import QgsGeometry, QgsWkbTypes

    parts = []
    if not geom or geom.isEmpty():
        return parts

    geom_type = geom.type()

    if geom_type == QgsWkbTypes.PolygonGeometry:
        if geom.isMultipart():
            for polygon in geom.asMultiPolygon():
                parts.append(QgsGeometry.fromPolygonXY(polygon))
        else:
            parts.append(geom)
    elif geom_type == QgsWkbTypes.UnknownGeometry:
        try:
            if geom.isMultipart():
                for polygon in geom.asMultiPolygon():
                    pg = QgsGeometry.fromPolygonXY(polygon)
                    if pg.type() == QgsWkbTypes.PolygonGeometry and pg.area() > 0:
                        parts.append(pg)
            elif geom.type() == QgsWkbTypes.PolygonGeometry:
                parts.append(geom)
        except Exception:
            pass

    return parts


def collect_interior_holes(union, gaps: list, tolerance: float):
    from qgis.core import QgsGeometry

    if union.isMultipart():
        for polygon in union.asMultiPolygon():
            for interior_ring in polygon[1:]:
                gap_geom = QgsGeometry.fromPolygonXY([interior_ring])
                if gap_geom.area() > tolerance:
                    gaps.append(gap_geom)
    else:
        polygon = union.asPolygon()
        if polygon and len(polygon) > 1:
            for interior_ring in polygon[1:]:
                gap_geom = QgsGeometry.fromPolygonXY([interior_ring])
                if gap_geom.area() > tolerance:
                    gaps.append(gap_geom)


def collect_gap_polygons(
    diff,
    original_geoms: list,
    gaps: list,
    tolerance: float,
    buffer_dist: float,
):
    from qgis.core import QgsGeometry, QgsWkbTypes

    parts = []
    if diff.isMultipart():
        for polygon in diff.asMultiPolygon():
            parts.append(QgsGeometry.fromPolygonXY(polygon))
    else:
        if diff.type() == QgsWkbTypes.PolygonGeometry:
            parts.append(diff)

    for part in parts:
        if part.area() <= tolerance:
            continue

        test_geom = part.buffer(buffer_dist * 0.5, 4)
        adjacent_count = sum(1 for g in original_geoms if test_geom.intersects(g))
        if adjacent_count >= 2:
            gaps.append(part)
