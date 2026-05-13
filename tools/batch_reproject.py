import logging
import os
from typing import Any, Callable, Dict, List, Optional

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
)

from ._utils import find_layer, resolve_input

logger = logging.getLogger("QgisAgent")


def run_batch_reproject(
    layer_names: List[str],
    target_crs: str,
    output_dir: Optional[str] = None,
    _confirm_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Batch reproject multiple layers to a target CRS.

    Args:
        layer_names: List of layer names to reproject.
        target_crs: Target CRS string, e.g. 'EPSG:4490'.
        output_dir: Optional output directory. If None, layers are added to project.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    crs = QgsCoordinateReferenceSystem(target_crs)
    if not crs.isValid():
        return {"success": False, "error": f"无效的 CRS: {target_crs}"}

    logger.info(f"Target CRS resolved: {crs.authid()} ({crs.description()})")

    if output_dir and not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            return {"success": False, "error": f"无法创建输出目录: {e}"}

    results = []
    errors = []
    skipped = []

    for layer_name in layer_names:
        layer = find_layer(layer_name)
        if layer is None:
            skipped.append(f"{layer_name} (图层不存在)")
            continue

        if not layer.isValid():
            skipped.append(f"{layer_name} (图层无效，数据源可能已损坏)")
            continue

        if not isinstance(layer, QgsVectorLayer):
            skipped.append(f"{layer_name} (非矢量图层，坐标转换仅支持矢量图层)")
            continue

        source_crs = layer.crs()
        if not source_crs.isValid():
            skipped.append(f"{layer_name} (源 CRS 无效)")
            continue

        if source_crs == crs:
            skipped.append(f"{layer_name} (已是目标 CRS)")
            continue

        raw_count = layer.featureCount()
        feature_count_before = raw_count if raw_count >= 0 else None

        try:
            input_value = resolve_input(layer)

            params = {
                "INPUT": input_value,
                "TARGET_CRS": crs,
                "OUTPUT": "memory:",
            }

            if output_dir:
                ext = ".shp"
                out_path = os.path.join(output_dir, f"{layer_name}_reprojected{ext}")
                if os.path.exists(out_path):
                    if _confirm_callback:
                        result = _confirm_callback(
                            f"文件已存在，是否覆盖？\n\n{out_path}"
                        )
                        if not result.confirmed:
                            skipped.append(f"{layer_name} (用户取消覆盖)")
                            continue
                    base = os.path.splitext(out_path)[0]
                    for suffix in (".shp", ".shx", ".dbf", ".prj", ".qpj", ".cpg", ".sbn", ".sbx"):
                        companion = base + suffix
                        if os.path.exists(companion):
                            os.remove(companion)
                params["OUTPUT"] = out_path

            import processing
            result = processing.run("native:reprojectlayer", params)

            crs_suffix = target_crs.split(':')[1] if ':' in target_crs else target_crs

            if result and "OUTPUT" in result:
                output_layer = result["OUTPUT"]
                if isinstance(output_layer, str):
                    out_name = f"{layer_name}_{crs_suffix}"
                    output_layer = QgsVectorLayer(output_layer, out_name, "ogr")
                    project.addMapLayer(output_layer)
                else:
                    output_layer.setName(f"{layer_name}_{crs_suffix}")
                    project.addMapLayer(output_layer)

                raw_after = output_layer.featureCount()
                feature_count_after = raw_after if raw_after >= 0 else None

                output_crs = output_layer.crs()
                crs_mismatch = False
                if output_crs.isValid() and crs.isValid():
                    if output_crs.authid() != crs.authid():
                        crs_mismatch = True
                        logger.warning(
                            f"CRS mismatch for '{layer_name}': "
                            f"expected {crs.authid()} ({crs.description()}), "
                            f"got {output_crs.authid()} ({output_crs.description()})"
                        )

                results.append({
                    "input": layer_name,
                    "output": output_layer.name(),
                    "features_before": feature_count_before,
                    "features_after": feature_count_after,
                    "source_crs": _crs_str(source_crs),
                    "target_crs": _crs_str(crs),
                    "output_crs": _crs_str(output_crs),
                    "crs_mismatch": crs_mismatch,
                })
            else:
                errors.append(f"{layer_name}: Processing 返回空结果")

        except Exception as e:
            logger.exception(f"Reproject error for layer '{layer_name}'")
            errors.append(f"{layer_name}: {str(e)}")

    success = len(results) > 0
    msg_parts = []
    if results:
        msg_parts.append(f"成功转换 {len(results)} 个图层到 {crs.authid()} ({crs.description()})")
    crs_warnings = [r for r in results if r.get("crs_mismatch")]
    if crs_warnings:
        warn_details = "; ".join(
            f"{r['input']}: 期望 {r['target_crs']}, 实际 {r['output_crs']}"
            for r in crs_warnings
        )
        msg_parts.append(f"⚠ CRS 不匹配: {warn_details}")
    if skipped:
        msg_parts.append(f"跳过 {len(skipped)} 个: {', '.join(skipped)}")
    if errors:
        msg_parts.append(f"失败 {len(errors)} 个: {'; '.join(errors)}")

    return {
        "success": success,
        "message": "，".join(msg_parts),
        "target_crs_info": _crs_str(crs),
        "results": results,
        "errors": errors,
        "skipped": skipped,
    }


def _crs_str(crs: QgsCoordinateReferenceSystem) -> str:
    if not crs.isValid():
        return "未知"
    return f"{crs.authid()} ({crs.description()})"
