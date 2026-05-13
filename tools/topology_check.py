"""Topology check tool for QGIS Agent."""

import logging
import math
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
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
    get_cross_layer_rules,
    extract_polygon_parts,
    collect_interior_holes,
    collect_gap_polygons,
)

from ._utils import find_layer

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
    layer = find_layer(layer_name)
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
    cross_layer_rules = get_cross_layer_rules()
    has_cross_layer_rule = any(r in cross_layer_rules for r in resolved_rules)

    if has_cross_layer_rule and reference_layer is None:
        return {
            "success": False,
            "error": "跨图层规则需要指定参考图层，请添加 reference_layer 参数",
        }

    ref_layer = None
    if reference_layer:
        ref_layer = find_layer(reference_layer)
        if ref_layer is None:
            return {"success": False, "error": f"参考图层 '{reference_layer}' 不存在"}

    # 执行各项检查
    all_errors: List[Tuple[str, str, QgsGeometry]] = []  # (error_type, description, geometry)

    for rule in resolved_rules:
        _, error_type, description, _, _ = TOPOLOGY_RULES[rule]

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

    QgsProject.instance().addMapLayer(output_layer)

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

    方法1：合并所有面，检查内部孔洞（完全被面包围的缝隙）。
    方法2：缓冲-反缓冲方法检测相邻面之间的小缝隙。
    仅对面图层有效。
    """
    if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        logger.warning("no_gaps 规则仅适用于面图层，当前图层已跳过")
        return []

    features = list(layer.getFeatures())
    geoms = [f.geometry() for f in features if f.geometry() and not f.geometry().isEmpty()]

    if len(geoms) < 2:
        return []

    union = QgsGeometry.unaryUnion(geoms)

    if not union or union.isEmpty():
        return []

    gaps = []

    collect_interior_holes(union, gaps, tolerance)

    buffer_dist = max(math.sqrt(tolerance) * 5, 0.01)
    buffered = union.buffer(buffer_dist, 8)
    if buffered and not buffered.isEmpty():
        smoothed = buffered.buffer(-buffer_dist, 8)
        if smoothed and not smoothed.isEmpty():
            diff = smoothed.difference(union)
            if diff and not diff.isEmpty():
                collect_gap_polygons(diff, geoms, gaps, tolerance, buffer_dist)

    return gaps


def _check_no_overlaps(layer: QgsVectorLayer) -> List[QgsGeometry]:
    """检测面要素之间的重叠。

    原理：用空间索引找出相交的要素对，计算交集。
    对多面重叠区域进行合并去重，避免同一区域被多次报告。
    仅对面图层有效，线图层和点图层不适用。
    """
    if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        logger.warning("no_overlaps 规则仅适用于面图层，当前图层已跳过")
        return []

    features = list(layer.getFeatures())
    if len(features) < 2:
        return []

    index = QgsSpatialIndex()
    feature_dict = {}
    for f in features:
        index.insertFeature(f)
        feature_dict[f.id()] = f

    overlap_parts = []
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
                    polygon_parts = extract_polygon_parts(intersection)
                    for part in polygon_parts:
                        if part.area() > 0:
                            overlap_parts.append(part)

    if not overlap_parts:
        return []

    # 合并所有重叠区域以去除重复
    merged = QgsGeometry.unaryUnion(overlap_parts)
    if not merged or merged.isEmpty():
        return []

    return extract_polygon_parts(merged)


def _check_no_dangles(layer: QgsVectorLayer, threshold: float) -> List[QgsGeometry]:
    """检测线要素的悬挂节点。

    原理：收集所有线的端点，只连接了1条线的端点就是悬挂节点。
    从悬挂端点沿折线找到第一个非悬挂节点，只提取悬挂段的几何。
    仅返回悬挂段长度小于 threshold 的悬挂（短悬挂是错误，长悬挂可能是正常要素）。
    """
    if layer.geometryType() != QgsWkbTypes.LineGeometry:
        logger.warning("no_dangles 规则仅适用于线图层，当前图层已跳过")
        return []

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

    # 收集所有非悬挂端点（连接了2条及以上线的端点）
    non_dangle_endpoints = set()
    for (x, y), fids in endpoint_features.items():
        if len(fids) >= 2:
            non_dangle_endpoints.add((x, y))

    dangle_endpoints = set()
    for (x, y), fids in endpoint_features.items():
        if len(fids) == 1:
            dangle_endpoints.add((x, y))

    if not dangle_endpoints:
        return []

    dangles = []
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

            # 从悬挂端点开始，沿折线找到第一个非悬挂节点
            if start in dangle_endpoints:
                dangle_segment = _extract_dangle_segment(line, from_start=True, non_dangle_endpoints=non_dangle_endpoints)
                if dangle_segment and dangle_segment.length() < threshold:
                    dangles.append(dangle_segment)

            if end in dangle_endpoints and start != end:
                dangle_segment = _extract_dangle_segment(line, from_start=False, non_dangle_endpoints=non_dangle_endpoints)
                if dangle_segment and dangle_segment.length() < threshold:
                    dangles.append(dangle_segment)

    return dangles


def _extract_dangle_segment(
    line: list,
    from_start: bool,
    non_dangle_endpoints: set,
) -> Optional[QgsGeometry]:
    """从折线中提取悬挂段几何。

    从悬挂端点出发，沿折线前进，找到第一个非悬挂节点为止，
    该段即为悬挂段。

    Args:
        line: 折线点列表 [QgsPointXY, ...]。
        from_start: True 则从起点（悬挂端）开始，False 则从终点（悬挂端）开始。
        non_dangle_endpoints: 非悬挂端点集合。

    Returns:
        悬挂段的 QgsGeometry，或 None。
    """
    if from_start:
        points = line
    else:
        points = list(reversed(line))

    segment_points = [points[0]]
    for i in range(1, len(points)):
        pt = points[i]
        segment_points.append(pt)
        coord = (round(pt.x(), 8), round(pt.y(), 8))
        if coord in non_dangle_endpoints:
            break

    if len(segment_points) < 2:
        return None

    return QgsGeometry.fromPolylineXY(segment_points)


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
    仅对点图层有效。
    """
    if layer.geometryType() != QgsWkbTypes.PointGeometry:
        logger.warning("no_duplicate_points 规则仅适用于点图层，当前图层已跳过")
        return []

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

    伪节点：端点只连接了2条不同的线要素，且两条线的属性完全相同。
    属性相同的线在伪节点处可以合并为一条，因此伪节点是拓扑错误。
    属性不同的线在端点相交是正常的交叉，不算伪节点。
    仅对线图层有效。
    """
    if layer.geometryType() != QgsWkbTypes.LineGeometry:
        logger.warning("no_pseudo_nodes 规则仅适用于线图层，当前图层已跳过")
        return []

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

    feature_dict = {f.id(): f for f in features}

    pseudo_nodes = []
    for (x, y), fids in endpoint_features.items():
        unique_fids = list(set(fids))
        if len(unique_fids) != 2:
            continue

        f1 = feature_dict.get(unique_fids[0])
        f2 = feature_dict.get(unique_fids[1])
        if f1 is None or f2 is None:
            continue

        # 检查两条线的属性是否相同（可合并的才算是伪节点）
        if _features_have_same_attributes(f1, f2):
            pseudo_nodes.append(QgsGeometry.fromPointXY(QgsPointXY(x, y)))

    return pseudo_nodes


def _features_have_same_attributes(f1: QgsFeature, f2: QgsFeature) -> bool:
    """检查两个要素的所有属性是否相同。

    Args:
        f1: 第一个要素。
        f2: 第二个要素。

    Returns:
        True 如果所有属性值相同。
    """
    fields1 = f1.fields()
    fields2 = f2.fields()
    if len(fields1) != len(fields2):
        return False

    for i in range(len(fields1)):
        v1 = f1.attribute(i)
        v2 = f2.attribute(i)
        if v1 != v2:
            return False

    return True


def _check_point_in_polygon(
    point_layer: QgsVectorLayer, polygon_layer: QgsVectorLayer
) -> List[QgsGeometry]:
    """检测不在面内的点。"""
    geoms = [f.geometry() for f in polygon_layer.getFeatures()
             if f.geometry() and not f.geometry().isEmpty()]

    if not geoms:
        return []

    polygon_union = QgsGeometry.unaryUnion(geoms)

    if not polygon_union or polygon_union.isEmpty():
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
    geoms = [f.geometry() for f in polygon_layer.getFeatures()
             if f.geometry() and not f.geometry().isEmpty()]

    if not geoms:
        return []

    polygon_union = QgsGeometry.unaryUnion(geoms)

    if not polygon_union or polygon_union.isEmpty():
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
    layer_geoms = [f.geometry() for f in layer.getFeatures()
                   if f.geometry() and not f.geometry().isEmpty()]
    ref_geoms = [f.geometry() for f in reference_layer.getFeatures()
                 if f.geometry() and not f.geometry().isEmpty()]

    if not layer_geoms or not ref_geoms:
        return []

    layer_union = QgsGeometry.unaryUnion(layer_geoms)
    ref_union = QgsGeometry.unaryUnion(ref_geoms)

    if not layer_union or layer_union.isEmpty() or not ref_union or ref_union.isEmpty():
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
        error_geom_types = set()
        for _, _, geom in errors:
            if geom and not geom.isEmpty():
                error_geom_types.add(geom.type())

        if QgsWkbTypes.PolygonGeometry in error_geom_types:
            type_str = "Polygon"
        elif QgsWkbTypes.LineGeometry in error_geom_types:
            type_str = "LineString"
        else:
            type_str = "Point"

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

