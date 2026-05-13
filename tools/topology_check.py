"""Topology check tool for QGIS Agent."""

import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsSpatialIndex,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

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
        reference_layer: Reference layer for cross-layer rules.
        dangle_threshold: Minimum length for dangle detection.
        gap_tolerance: Minimum area for gap detection.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    layer = _find_layer(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    if not isinstance(layer, QgsVectorLayer):
        return {"success": False, "error": f"图层 '{layer_name}' 不是矢量图层"}

    geom_type = get_geometry_type_name(layer)

    # 解析规则
    if rules is None:
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
            "error": "跨图层规则需要指定参考图层，请添加 reference_layer 参数",
        }

    ref_layer = None
    if reference_layer:
        ref_layer = _find_layer(reference_layer)
        if ref_layer is None:
            return {"success": False, "error": f"参考图层 '{reference_layer}' 不存在"}

    # 执行各项检查
    all_errors: List[Tuple[str, str, QgsGeometry]] = []  # (error_type, description, geometry)

    for rule in resolved_rules:
        _, error_type, description, _ = TOPOLOGY_RULES[rule]

        try:
            if rule == "no_gaps":
                errors = _check_no_gaps(layer, gap_tolerance)
            elif rule == "no_overlaps":
                errors = _check_no_overlaps(layer)
            elif rule == "no_dangles":
                errors = _check_no_dangles(layer, dangle_threshold)
            elif rule == "no_self_intersections" or rule == "invalid_geometry":
                errors = _check_invalid_geometry(layer)
            elif rule == "no_duplicate_points":
                errors = _check_duplicate_points(layer)
            elif rule == "no_pseudo_nodes":
                errors = _check_pseudo_nodes(layer)
            elif rule == "point_in_polygon" and ref_layer:
                errors = _check_point_in_polygon(layer, ref_layer)
            elif rule == "line_in_polygon" and ref_layer:
                errors = _check_line_in_polygon(layer, ref_layer)
            elif rule == "polygon_coverage" and ref_layer:
                errors = _check_polygon_coverage(layer, ref_layer)
            else:
                continue

            for geom in errors:
                all_errors.append((error_type, description, geom))

        except Exception as e:
            logger.exception(f"Error checking rule '{rule}'")
            return {"success": False, "error": f"检查规则 '{rule}' 失败: {str(e)}"}

    # 无错误
    if not all_errors:
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

    # 汇总错误
    error_summary = {}
    for error_type, _, _ in all_errors:
        error_summary[error_type] = error_summary.get(error_type, 0) + 1

    # 创建错误输出图层
    output_layer_name = f"{layer_name}_topology_errors"
    output_layer = _create_error_layer(layer, all_errors, output_layer_name)

    if output_layer is None:
        return {"success": False, "error": "创建错误图层失败"}

    project.addMapLayer(output_layer)

    return {
        "success": True,
        "message": f"拓扑检查完成，发现 {len(all_errors)} 个错误",
        "results": [{
            "input": layer_name,
            "output": output_layer_name,
            "rules_checked": resolved_rules,
            "error_count": len(all_errors),
            "error_summary": error_summary,
        }],
    }


# ──────────────────────────────────────────────
# 各拓扑规则的检测实现
# ──────────────────────────────────────────────

def _check_no_gaps(layer: QgsVectorLayer, tolerance: float) -> List[QgsGeometry]:
    """检测面要素之间的缝隙。

    原理：将所有面的边界提取为线，用 polygonize 重建封闭区域，
    然后用 重建区域 - 原始面 = 缝隙。
    """
    features = list(layer.getFeatures())
    geoms = [f.geometry() for f in features if f.geometry() and not f.geometry().isEmpty()]

    if len(geoms) < 2:
        return []

    # 提取所有面的边界线
    boundaries = []
    for g in geoms:
        boundary = g.boundary()
        if boundary and not boundary.isEmpty():
            boundaries.append(boundary)

    if not boundaries:
        return []

    # 用边界线重建封闭多边形
    polygonized = QgsGeometry.polygonize(boundaries)

    if not polygonized or polygonized.isEmpty():
        return []

    # 原始面的合并
    original_union = QgsGeometry.unaryUnion(geoms)

    # 缝隙 = 重建区域 - 原始面
    gaps = polygonized.difference(original_union)

    if not gaps or gaps.isEmpty():
        return []

    # 拆分为单个缝隙多边形，过滤掉太小的
    gap_list = []
    if gaps.isMultipart():
        for polygon in gaps.asMultiPolygon():
            gap_geom = QgsGeometry.fromPolygonXY(polygon)
            if gap_geom.area() > tolerance:
                gap_list.append(gap_geom)
    else:
        if gaps.area() > tolerance:
            gap_list.append(gaps)

    return gap_list


def _check_no_overlaps(layer: QgsVectorLayer) -> List[QgsGeometry]:
    """检测面要素之间的重叠。

    原理：用空间索引找出相交的要素对，计算交集。
    """
    features = list(layer.getFeatures())
    if len(features) < 2:
        return []

    index = QgsSpatialIndex()
    feature_dict = {}
    for f in features:
        index.insertFeature(f)
        feature_dict[f.id()] = f

    overlaps = []
    checked = set()

    for f in features:
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue

        candidates = index.intersects(geom.boundingBox())
        for cand_id in candidates:
            if cand_id == f.id():
                continue

            pair = (min(f.id(), cand_id), max(f.id(), cand_id))
            if pair in checked:
                continue
            checked.add(pair)

            cand = feature_dict.get(cand_id)
            if cand is None:
                continue

            cand_geom = cand.geometry()
            if cand_geom is None or cand_geom.isEmpty():
                continue

            if geom.intersects(cand_geom) and not geom.touches(cand_geom):
                intersection = geom.intersection(cand_geom)
                if intersection and not intersection.isEmpty():
                    # 只保留面积型交集（真正的重叠）
                    if intersection.type() == QgsWkbTypes.PolygonGeometry:
                        if intersection.area() > 0:
                            overlaps.append(intersection)

    return overlaps


def _check_no_dangles(layer: QgsVectorLayer, threshold: float) -> List[QgsGeometry]:
    """检测线要素的悬挂节点。

    原理：收集所有线的端点，只连接了1条线的端点就是悬挂节点。
    """
    features = list(layer.getFeatures())

    # 收集所有端点及其关联的要素
    endpoint_features: Dict[Tuple[float, float], List[int]] = defaultdict(list)

    for f in features:
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue

        lines = []
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
        else:
            line = geom.asPolyline()
            if line:
                lines = [line]

        for line in lines:
            if len(line) < 2:
                continue
            start = (round(line[0].x(), 8), round(line[0].y(), 8))
            end = (round(line[-1].x(), 8), round(line[-1].y(), 8))
            endpoint_features[start].append(f.id())
            endpoint_features[end].append(f.id())

    # 只连接1条线的端点 = 悬挂节点
    dangles = []
    for (x, y), fids in endpoint_features.items():
        if len(fids) == 1:
            dangles.append(QgsGeometry.fromPointXY(QgsPointXY(x, y)))

    return dangles


def _check_invalid_geometry(layer: QgsVectorLayer) -> List[QgsGeometry]:
    """检测无效几何（自相交等）。

    原理：用 GEOS 库验证几何有效性。
    """
    errors = []
    for f in layer.getFeatures():
        geom = f.geometry()
        if geom and not geom.isEmpty() and not geom.isGeosValid():
            errors.append(geom)
    return errors


def _check_duplicate_points(layer: QgsVectorLayer) -> List[QgsGeometry]:
    """检测重复的点要素。

    原理：用空间索引查找位置相同的点。
    """
    features = list(layer.getFeatures())
    if len(features) < 2:
        return []

    index = QgsSpatialIndex()
    feature_dict = {}
    for f in features:
        index.insertFeature(f)
        feature_dict[f.id()] = f

    duplicates = []
    checked = set()

    for f in features:
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue

        candidates = index.intersects(geom.boundingBox())
        for cand_id in candidates:
            if cand_id == f.id():
                continue

            pair = (min(f.id(), cand_id), max(f.id(), cand_id))
            if pair in checked:
                continue
            checked.add(pair)

            cand = feature_dict.get(cand_id)
            if cand is None:
                continue

            if geom.equals(cand.geometry()):
                duplicates.append(geom)

    return duplicates


def _check_pseudo_nodes(layer: QgsVectorLayer) -> List[QgsGeometry]:
    """检测线要素的伪节点。

    伪节点：一条线的端点只连接了另一条线（除了自身），且两条线属性相同。
    这里简化为：端点只连接了2条线（包括自身）的情况。
    """
    features = list(layer.getFeatures())

    endpoint_features: Dict[Tuple[float, float], List[int]] = defaultdict(list)

    for f in features:
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue

        lines = []
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
        else:
            line = geom.asPolyline()
            if line:
                lines = [line]

        for line in lines:
            if len(line) < 2:
                continue
            start = (round(line[0].x(), 8), round(line[0].y(), 8))
            end = (round(line[-1].x(), 8), round(line[-1].y(), 8))
            endpoint_features[start].append(f.id())
            endpoint_features[end].append(f.id())

    # 伪节点：端点只连接了2条线
    pseudo_nodes = []
    for (x, y), fids in endpoint_features.items():
        unique_fids = list(set(fids))
        if len(unique_fids) == 2:
            pseudo_nodes.append(QgsGeometry.fromPointXY(QgsPointXY(x, y)))

    return pseudo_nodes


def _check_point_in_polygon(
    point_layer: QgsVectorLayer, polygon_layer: QgsVectorLayer
) -> List[QgsGeometry]:
    """检测不在面内的点。"""
    polygon_union = None
    for f in polygon_layer.getFeatures():
        geom = f.geometry()
        if geom and not geom.isEmpty():
            if polygon_union is None:
                polygon_union = QgsGeometry(geom)
            else:
                polygon_union = polygon_union.combine(geom)

    if polygon_union is None:
        return []

    errors = []
    for f in point_layer.getFeatures():
        geom = f.geometry()
        if geom and not geom.isEmpty():
            if not polygon_union.contains(geom):
                errors.append(geom)

    return errors


def _check_line_in_polygon(
    line_layer: QgsVectorLayer, polygon_layer: QgsVectorLayer
) -> List[QgsGeometry]:
    """检测不在面内的线。"""
    polygon_union = None
    for f in polygon_layer.getFeatures():
        geom = f.geometry()
        if geom and not geom.isEmpty():
            if polygon_union is None:
                polygon_union = QgsGeometry(geom)
            else:
                polygon_union = polygon_union.combine(geom)

    if polygon_union is None:
        return []

    errors = []
    for f in line_layer.getFeatures():
        geom = f.geometry()
        if geom and not geom.isEmpty():
            diff = geom.difference(polygon_union)
            if diff and not diff.isEmpty():
                errors.append(diff)

    return errors


def _check_polygon_coverage(
    layer: QgsVectorLayer, reference_layer: QgsVectorLayer
) -> List[QgsGeometry]:
    """检测面图层未被参考面图层覆盖的区域。"""
    layer_union = None
    for f in layer.getFeatures():
        geom = f.geometry()
        if geom and not geom.isEmpty():
            if layer_union is None:
                layer_union = QgsGeometry(geom)
            else:
                layer_union = layer_union.combine(geom)

    ref_union = None
    for f in reference_layer.getFeatures():
        geom = f.geometry()
        if geom and not geom.isEmpty():
            if ref_union is None:
                ref_union = QgsGeometry(geom)
            else:
                ref_union = ref_union.combine(geom)

    if layer_union is None or ref_union is None:
        return []

    uncovered = ref_union.difference(layer_union)
    if uncovered and not uncovered.isEmpty():
        return [uncovered]

    return []


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

def _create_error_layer(
    source_layer: QgsVectorLayer,
    errors: List[Tuple[str, str, QgsGeometry]],
    output_name: str,
) -> Optional[QgsVectorLayer]:
    """创建包含拓扑错误要素的新图层。"""
    try:
        # 根据源图层几何类型决定输出图层类型
        geom_type = source_layer.geometryType()
        if geom_type == QgsWkbTypes.PointGeometry:
            type_str = "Point"
        elif geom_type == QgsWkbTypes.LineGeometry:
            type_str = "LineString"
        else:
            type_str = "Polygon"

        output_layer = QgsVectorLayer(
            f"{type_str}?crs={source_layer.crs().authid()}",
            output_name,
            "memory",
        )

        if not output_layer.isValid():
            return None

        provider = output_layer.dataProvider()
        provider.addAttributes([
            QgsField("error_id", QVariant.Int),
            QgsField("error_type", QVariant.String),
            QgsField("error_description", QVariant.String),
            QgsField("layer_name", QVariant.String),
        ])
        output_layer.updateFields()

        output_layer.startEditing()
        for idx, (error_type, description, geom) in enumerate(errors):
            new_feature = QgsFeature(output_layer.fields())
            new_feature.setGeometry(geom)
            new_feature.setAttribute("error_id", idx + 1)
            new_feature.setAttribute("error_type", error_type)
            new_feature.setAttribute("error_description", description)
            new_feature.setAttribute("layer_name", source_layer.name())
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
