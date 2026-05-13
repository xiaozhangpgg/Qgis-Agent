"""Topology fix tool for QGIS Agent."""

import logging
import math
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsSpatialIndex,
)

import processing

from .topology_rules import (
    TOPOLOGY_RULES,
    FIX_STRATEGIES,
    DEFAULT_DANGLE_THRESHOLD,
    DEFAULT_GAP_TOLERANCE,
    DEFAULT_OVERLAP_STRATEGY,
    get_geometry_type_name,
    get_rules_for_geometry_type,
    extract_polygon_parts,
    collect_interior_holes,
    collect_gap_polygons,
)

from ._utils import find_layer

logger = logging.getLogger("QgisAgent")

FIX_PRIORITY = [
    "invalid_geometry",
    "self_intersection",
    "duplicate_point",
    "overlap",
    "gap",
    "dangle",
    "pseudo_node",
]


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
        _confirm_callback: Optional callback for user confirmation before destructive fixes.

    Returns:
        Dict with 'success', 'message', 'results' keys.
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

    geom_type = get_geometry_type_name(layer)

    if error_types is None:
        fix_types = [
            ft for ft in get_rules_for_geometry_type(geom_type) if ft in FIX_STRATEGIES
        ]
    else:
        fix_types = []
        for et in error_types:
            if et not in FIX_STRATEGIES:
                return {
                    "success": False,
                    "error": f"不支持修复的错误类型 '{et}'，支持: {', '.join(FIX_STRATEGIES.keys())}",
                }
            fix_types.append(et)

    applicable_fixes = []
    for ft in fix_types:
        if ft in TOPOLOGY_RULES:
            _, _, _, applicable_type = TOPOLOGY_RULES[ft]
            if applicable_type == "all" or applicable_type == geom_type:
                applicable_fixes.append(ft)
            else:
                logger.warning(
                    f"跳过不适用的修复类型 '{ft}'（图层类型: {geom_type}，需要: {applicable_type}）"
                )
    fix_types = applicable_fixes

    if not fix_types:
        return {"success": False, "error": "没有适用的修复类型"}

    fix_types = sorted(
        fix_types,
        key=lambda ft: FIX_PRIORITY.index(ft) if ft in FIX_PRIORITY else len(FIX_PRIORITY),
    )

    if _confirm_callback:
        approved = _confirm_callback(
            f"即将对图层 '{layer_name}' 执行以下修复: {', '.join(fix_types)}",
            fix_types,
        )
        if not approved:
            return {"success": False, "error": "用户取消了修复操作"}

    invalid_count_before = _count_invalid_geometries(layer)
    feature_count_before = layer.featureCount() if hasattr(layer, "featureCount") else 0

    current_layer = layer
    fix_summary: Dict[str, str] = {}

    for fix_type in fix_types:
        strategy = FIX_STRATEGIES[fix_type]
        try:
            result_layer = _apply_fix(
                current_layer,
                fix_type,
                strategy,
                dangle_threshold=dangle_threshold,
                gap_tolerance=gap_tolerance,
                overlap_strategy=overlap_strategy,
            )
            if result_layer is not None:
                current_layer = result_layer
                fix_summary[fix_type] = "已修复"
            else:
                fix_summary[fix_type] = "无需修复"
        except Exception as e:
            logger.exception(f"Fix error for type '{fix_type}'")
            fix_summary[fix_type] = f"修复失败: {str(e)}"

    output_name = f"{layer_name}_fixed"
    current_layer.setName(output_name)
    project.addMapLayer(current_layer)

    invalid_count_after = _count_invalid_geometries(current_layer)
    feature_count_after = current_layer.featureCount()
    errors_fixed = max(0, invalid_count_before - invalid_count_after)

    return {
        "success": True,
        "message": f"拓扑修复完成，输出图层 '{output_name}'",
        "results": [
            {
                "input": layer_name,
                "output": output_name,
                "errors_fixed": errors_fixed,
                "fix_summary": fix_summary,
                "features_before": feature_count_before,
                "features_after": feature_count_after,
            }
        ],
    }


def _apply_fix(
    layer: QgsVectorLayer,
    fix_type: str,
    strategy: str,
    dangle_threshold: float = DEFAULT_DANGLE_THRESHOLD,
    gap_tolerance: float = DEFAULT_GAP_TOLERANCE,
    overlap_strategy: str = DEFAULT_OVERLAP_STRATEGY,
) -> Optional[QgsVectorLayer]:
    if strategy == "fix_geometries":
        return _run_processing(layer, "native:fixgeometries")

    if strategy == "remove_duplicates":
        return _run_processing(layer, "native:deleteduplicategeometries")

    if strategy == "difference":
        return _fix_overlaps(layer, overlap_strategy)

    if strategy == "buffer_dissolve":
        return _fix_gaps(layer, gap_tolerance)

    if strategy == "extract_delete":
        if fix_type == "dangle":
            return _fix_dangles(layer, dangle_threshold)
        if fix_type == "pseudo_node":
            return _fix_pseudo_nodes(layer)

    return None


def _run_processing(layer: QgsVectorLayer, algorithm_id: str) -> Optional[QgsVectorLayer]:
    params = {"INPUT": layer, "OUTPUT": "memory:"}
    result = processing.run(algorithm_id, params)
    if result and "OUTPUT" in result:
        output = result["OUTPUT"]
        if output and output.isValid():
            return output
    return None


def _fix_overlaps(layer: QgsVectorLayer, strategy: str) -> Optional[QgsVectorLayer]:
    if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        return None

    if strategy == "merge":
        return _run_processing(layer, "native:dissolve")

    features = list(layer.getFeatures())
    if len(features) < 2:
        return None

    index = QgsSpatialIndex()
    feature_dict = {}
    for f in features:
        index.insertFeature(f)
        feature_dict[f.id()] = f

    modified_geoms: Dict[int, QgsGeometry] = {}
    checked: Set[tuple] = set()

    for f in features:
        current_geom = modified_geoms.get(f.id(), f.geometry())
        if current_geom is None or current_geom.isEmpty():
            continue

        candidates = index.intersects(f.geometry().boundingBox())
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

            cand_geom = modified_geoms.get(cand_id, cand.geometry())
            if cand_geom is None or cand_geom.isEmpty():
                continue

            if current_geom.intersects(cand_geom) and not current_geom.touches(cand_geom):
                intersection = current_geom.intersection(cand_geom)
                if intersection is None or intersection.isEmpty():
                    continue

                poly_parts = extract_polygon_parts(intersection)
                if not poly_parts:
                    continue

                area_current = current_geom.area()
                area_cand = cand_geom.area()

                if area_current <= area_cand:
                    diff = current_geom.difference(cand_geom)
                    if diff and not diff.isEmpty():
                        modified_geoms[f.id()] = diff
                        current_geom = diff
                else:
                    diff = cand_geom.difference(current_geom)
                    if diff and not diff.isEmpty():
                        modified_geoms[cand_id] = diff

    if not modified_geoms:
        return None

    return _create_fixed_layer(layer, features, modified_geoms)


def _fix_gaps(layer: QgsVectorLayer, tolerance: float) -> Optional[QgsVectorLayer]:
    if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        return None

    features = list(layer.getFeatures())
    geoms = [f.geometry() for f in features if f.geometry() and not f.geometry().isEmpty()]

    if len(geoms) < 2:
        return None

    union = QgsGeometry.unaryUnion(geoms)
    if not union or union.isEmpty():
        return None

    gaps: List[QgsGeometry] = []
    collect_interior_holes(union, gaps, tolerance)

    if not gaps:
        buffer_dist = max(math.sqrt(tolerance) * 5, 0.01)
        buffered = union.buffer(buffer_dist, 8)
        if buffered and not buffered.isEmpty():
            smoothed = buffered.buffer(-buffer_dist, 8)
            if smoothed and not smoothed.isEmpty():
                diff = smoothed.difference(union)
                if diff and not diff.isEmpty():
                    collect_gap_polygons(diff, geoms, gaps, tolerance, buffer_dist)

    if not gaps:
        return None

    modified_geoms: Dict[int, QgsGeometry] = {}
    gap_buffer_dist = max(tolerance * 10, 0.001)

    for gap in gaps:
        gap_buffered = gap.buffer(gap_buffer_dist, 4)
        best_fid = None
        best_overlap = 0.0

        for f in features:
            geom = modified_geoms.get(f.id(), f.geometry())
            if geom is None or geom.isEmpty():
                continue

            if gap_buffered.intersects(geom):
                inter = gap_buffered.intersection(geom)
                if inter and not inter.isEmpty():
                    area = inter.area()
                    if area > best_overlap:
                        best_overlap = area
                        best_fid = f.id()

        if best_fid is not None:
            current_geom = modified_geoms.get(best_fid, None)
            if current_geom is None:
                for f in features:
                    if f.id() == best_fid:
                        current_geom = f.geometry()
                        break

            if current_geom is not None:
                merged = current_geom.combine(gap)
                if merged and not merged.isEmpty():
                    modified_geoms[best_fid] = merged

    if not modified_geoms:
        return None

    return _create_fixed_layer(layer, features, modified_geoms)


def _fix_dangles(layer: QgsVectorLayer, threshold: float) -> Optional[QgsVectorLayer]:
    if layer.geometryType() != QgsWkbTypes.LineGeometry:
        return None

    features = list(layer.getFeatures())
    if not features:
        return None

    endpoint_features: Dict[tuple, List[int]] = defaultdict(list)

    for f in features:
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue
        for line in _iter_lines(geom):
            if len(line) < 2:
                continue
            start = (round(line[0].x(), 8), round(line[0].y(), 8))
            end = (round(line[-1].x(), 8), round(line[-1].y(), 8))
            endpoint_features[start].append(f.id())
            endpoint_features[end].append(f.id())

    dangle_endpoints: Set[tuple] = set()
    for (x, y), fids in endpoint_features.items():
        if len(set(fids)) == 1:
            dangle_endpoints.add((x, y))

    if not dangle_endpoints:
        return None

    features_to_remove: Set[int] = set()
    modified_geoms: Dict[int, QgsGeometry] = {}

    for f in features:
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue

        lines = list(_iter_lines(geom))

        has_short_dangle = False
        for line in lines:
            if len(line) < 2:
                continue
            start = (round(line[0].x(), 8), round(line[0].y(), 8))
            end = (round(line[-1].x(), 8), round(line[-1].y(), 8))
            seg_geom = QgsGeometry.fromPolylineXY(line)
            if (
                start in dangle_endpoints or end in dangle_endpoints
            ) and seg_geom.length() < threshold:
                has_short_dangle = True
                break

        if not has_short_dangle:
            continue

        if not geom.isMultipart():
            features_to_remove.add(f.id())
            continue

        remaining_lines = []
        for line in lines:
            if len(line) < 2:
                remaining_lines.append(line)
                continue
            start = (round(line[0].x(), 8), round(line[0].y(), 8))
            end = (round(line[-1].x(), 8), round(line[-1].y(), 8))
            seg_geom = QgsGeometry.fromPolylineXY(line)
            if (
                start in dangle_endpoints or end in dangle_endpoints
            ) and seg_geom.length() < threshold:
                continue
            remaining_lines.append(line)

        if not remaining_lines:
            features_to_remove.add(f.id())
        elif len(remaining_lines) == 1:
            modified_geoms[f.id()] = QgsGeometry.fromPolylineXY(remaining_lines[0])
        else:
            modified_geoms[f.id()] = QgsGeometry.fromMultiPolylineXY(remaining_lines)

    if not features_to_remove and not modified_geoms:
        return None

    return _create_fixed_layer(layer, features, modified_geoms, features_to_remove)


def _fix_pseudo_nodes(layer: QgsVectorLayer) -> Optional[QgsVectorLayer]:
    if layer.geometryType() != QgsWkbTypes.LineGeometry:
        return None

    params = {"INPUT": layer, "OUTPUT": "memory:"}
    result = processing.run("native:mergelines", params)
    if result and "OUTPUT" in result:
        output = result["OUTPUT"]
        if output and output.isValid():
            return output
    return None


def _count_invalid_geometries(layer: QgsVectorLayer) -> int:
    count = 0
    for f in layer.getFeatures():
        geom = f.geometry()
        if geom and not geom.isEmpty() and not geom.isGeosValid():
            count += 1
    return count


def _iter_lines(geom: QgsGeometry):
    if geom.isMultipart():
        return geom.asMultiPolyline()
    line = geom.asPolyline()
    return [line] if line else []


def _get_geom_string(layer: QgsVectorLayer) -> str:
    wkb = layer.wkbType()
    mapping = {
        QgsWkbTypes.Point: "Point",
        QgsWkbTypes.MultiPoint: "MultiPoint",
        QgsWkbTypes.LineString: "LineString",
        QgsWkbTypes.MultiLineString: "MultiLineString",
        QgsWkbTypes.Polygon: "Polygon",
        QgsWkbTypes.MultiPolygon: "MultiPolygon",
    }
    return mapping.get(wkb, "Polygon")


def _create_fixed_layer(
    source_layer: QgsVectorLayer,
    features: list,
    modified_geoms: Dict[int, QgsGeometry],
    removed_fids: Optional[Set[int]] = None,
) -> Optional[QgsVectorLayer]:
    try:
        geom_str = _get_geom_string(source_layer)
        output_layer = QgsVectorLayer(
            f"{geom_str}?crs={source_layer.crs().authid()}",
            source_layer.name(),
            "memory",
        )
        if not output_layer.isValid():
            return None

        provider = output_layer.dataProvider()
        provider.addAttributes(source_layer.fields().toList())
        output_layer.updateFields()

        removed = removed_fids or set()

        for f in features:
            if f.id() in removed:
                continue

            new_feature = QgsFeature(output_layer.fields())
            new_feature.setAttributes(f.attributes())

            if f.id() in modified_geoms:
                new_feature.setGeometry(modified_geoms[f.id()])
            else:
                new_feature.setGeometry(f.geometry())

            provider.addFeature(new_feature)

        return output_layer

    except Exception as e:
        logger.exception("Failed to create fixed layer")
        return None

