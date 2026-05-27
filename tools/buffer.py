import logging
from typing import Any, Callable, Dict, Optional

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
)

import processing

from ._utils import find_layer

logger = logging.getLogger("QgisAgent")


def run_buffer(
    layer_name: str,
    distance: float,
    segments: int = 25,
    dissolve: bool = False,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Create buffer zones around features in a layer.

    Args:
        layer_name: Input layer name.
        distance: Buffer distance in meters.
        segments: Number of segments for quarter circle (default 25).
        dissolve: Whether to dissolve overlapping buffers (default False).

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

    if distance <= 0:
        return {"success": False, "error": f"缓冲区距离必须大于 0，当前值: {distance}"}

    feature_count_before = layer.featureCount() if hasattr(layer, 'featureCount') else 0
    source_crs = layer.crs()

    try:
        if source_crs.isGeographic():
            target_crs = _find_suitable_projected_crs(layer)
            if target_crs is None:
                return {
                    "success": False,
                    "error": (
                        f"图层 '{layer_name}' 使用地理坐标系 ({source_crs.authid()})，"
                        "无法自动确定合适的投影坐标系进行缓冲区分析。"
                        "请先将图层重投影到投影坐标系（如 UTM），再执行缓冲区操作。"
                    ),
                }

            reprojected = processing.run("native:reprojectlayer", {
                "INPUT": layer,
                "TARGET_CRS": target_crs,
                "OUTPUT": "memory:",
            })
            if not reprojected or "OUTPUT" not in reprojected:
                return {"success": False, "error": "图层重投影失败"}

            input_for_buffer = reprojected["OUTPUT"]
        else:
            target_crs = None
            input_for_buffer = layer

        params = {
            "INPUT": input_for_buffer,
            "DISTANCE": distance,
            "SEGMENTS": segments,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "DISSOLVE": dissolve,
            "OUTPUT": "memory:",
        }

        result = processing.run("native:buffer", params)

        if result and "OUTPUT" in result:
            output_layer = result["OUTPUT"]

            if target_crs is not None:
                reprojected_back = processing.run("native:reprojectlayer", {
                    "INPUT": output_layer,
                    "TARGET_CRS": source_crs,
                    "OUTPUT": "memory:",
                })
                if reprojected_back and "OUTPUT" in reprojected_back:
                    output_layer = reprojected_back["OUTPUT"]
                else:
                    return {"success": False, "error": "缓冲区结果重投影回源坐标系失败"}

            output_layer.setName(f"{layer_name}_buffer_{int(distance)}")
            project.addMapLayer(output_layer)

            feature_count_after = output_layer.featureCount()

            crs_info = ""
            if target_crs is not None:
                crs_info = f"（已自动从 {source_crs.authid()} 重投影到 {target_crs.authid()} 执行缓冲区分析）"

            return {
                "success": True,
                "message": (
                    f"成功为 '{layer_name}' 创建 {distance} 米缓冲区，"
                    f"生成 {feature_count_after} 个要素{crs_info}"
                ),
                "results": [{
                    "input": layer_name,
                    "output": output_layer.name(),
                    "distance": distance,
                    "distance_unit": "meters",
                    "source_crs": source_crs.authid(),
                    "buffer_crs": target_crs.authid() if target_crs else source_crs.authid(),
                    "features_before": feature_count_before,
                    "features_after": feature_count_after,
                }],
            }
        else:
            return {"success": False, "error": "Processing 返回空结果"}

    except Exception as e:
        logger.exception(f"Buffer error for layer '{layer_name}'")
        return {"success": False, "error": f"缓冲区分析失败: {str(e)}"}


def _find_suitable_projected_crs(layer) -> Optional[QgsCoordinateReferenceSystem]:
    """Find a suitable projected CRS for buffering based on layer extent.

    Tries in order:
    1. Project CRS (if projected)
    2. UTM zone based on layer centroid
    """
    project = QgsProject.instance()
    project_crs = project.crs()
    if project_crs.isValid() and not project_crs.isGeographic():
        return project_crs

    try:
        extent = layer.extent()
        if extent.isEmpty():
            return None
        centroid = extent.center()
        lon = centroid.x()
        lat = centroid.y()
        utm_crs = _compute_utm_crs(lon, lat)
        if utm_crs is not None:
            return utm_crs
    except Exception:
        logger.exception("Failed to compute UTM CRS from layer extent")

    return None


def _compute_utm_crs(lon: float, lat: float) -> Optional[QgsCoordinateReferenceSystem]:
    """Compute the UTM CRS EPSG code for a given longitude/latitude."""
    zone_number = int((lon + 180) / 6) + 1
    if lat >= 0:
        epsg = 32600 + zone_number
    else:
        epsg = 32700 + zone_number
    crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg}")
    if crs.isValid():
        return crs
    return None

