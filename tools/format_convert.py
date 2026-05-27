import logging
import os
from typing import Any, Callable, Dict, Optional

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsVectorFileWriter,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRasterLayer,
)

import processing

from ._utils import (
    find_layer_case_insensitive,
    FORMAT_EXTENSIONS,
    DRIVER_MAP,
    RASTER_FORMAT_EXTENSIONS,
    is_raster_format,
)

logger = logging.getLogger("QgisAgent")

_WRITER_ERROR_MESSAGES = {
    QgsVectorFileWriter.ErrDriverNotFound: "OGR 驱动未找到",
    QgsVectorFileWriter.ErrCreateDataSource: "无法创建数据源",
    QgsVectorFileWriter.ErrCreateLayer: "无法创建图层",
    QgsVectorFileWriter.ErrAttributeTypeUnsupported: "属性类型不支持",
    QgsVectorFileWriter.ErrAttributeCreationFailed: "属性创建失败",
    QgsVectorFileWriter.ErrProjection: "投影错误",
    QgsVectorFileWriter.ErrFeatureWriteFailed: "要素写入失败",
    QgsVectorFileWriter.ErrInvalidLayer: "无效图层",
    QgsVectorFileWriter.ErrSavingMetadata: "元数据保存失败",
    QgsVectorFileWriter.Canceled: "操作已取消",
}


def _export_vector(
    layer: QgsVectorLayer,
    output_path: str,
    driver_name: str,
    target_crs: Optional[str] = None,
    only_selected: bool = False,
) -> Dict[str, Any]:
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    options.onlySelectedFeatures = only_selected

    if target_crs:
        crs = QgsCoordinateReferenceSystem(f"EPSG:{target_crs.lstrip('EPSG:')}")
        if crs.isValid():
            options.ct = QgsCoordinateTransform(
                layer.crs(), crs, QgsProject.instance().transformContext()
            )
        else:
            return {"success": False, "error": f"无效的目标 CRS: {target_crs}"}

    transform_context = QgsProject.instance().transformContext()
    error_code, error_msg, new_filename, new_layer = (
        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, output_path, transform_context, options
        )
    )

    if error_code == QgsVectorFileWriter.NoError:
        feature_count = layer.featureCount()
        return {
            "success": True,
            "output_path": new_filename or output_path,
            "feature_count": feature_count if not only_selected else layer.selectedFeatureCount(),
        }
    else:
        msg = _WRITER_ERROR_MESSAGES.get(error_code, f"未知错误 (code={error_code})")
        if error_msg:
            msg += f": {error_msg}"
        return {"success": False, "error": msg}


def _export_raster(
    layer: QgsRasterLayer,
    output_path: str,
) -> Dict[str, Any]:
    try:
        params = {
            "INPUT": layer,
            "OUTPUT": output_path,
        }
        result = processing.run("gdal:translate", params)
        if result and "OUTPUT" in result:
            return {"success": True, "output_path": result["OUTPUT"]}
        else:
            return {"success": False, "error": "GDAL Translate 返回空结果"}
    except Exception as e:
        return {"success": False, "error": f"栅格导出失败: {str(e)}"}


def run_format_convert(
    layer_name: str,
    output_format: str,
    output_path: str,
    target_crs: Optional[str] = None,
    only_selected: bool = False,
    _confirm_callback: Optional[Callable] = None,
    _ask_dir_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    layer = find_layer_case_insensitive(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    fmt = output_format.lower().strip().lstrip(".")

    if is_raster_format(fmt):
        if not isinstance(layer, QgsRasterLayer):
            return {"success": False, "error": f"图层 '{layer_name}' 不是栅格图层，无法导出为 {fmt}"}
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        if os.path.exists(output_path) and _confirm_callback:
            result = _confirm_callback(f"文件 '{output_path}' 已存在，是否覆盖？")
            if not result.confirmed:
                return {"success": False, "error": "用户取消覆盖"}

        res = _export_raster(layer, output_path)
        if res["success"]:
            return {
                "success": True,
                "message": f"已将栅格图层 '{layer_name}' 导出为 {fmt.upper()} 格式，保存到: {res['output_path']}",
                "results": [{
                    "input": layer_name,
                    "output_format": fmt,
                    "output_path": res["output_path"],
                    "layer_type": "raster",
                }],
            }
        else:
            return {"success": False, "error": res["error"]}

    if fmt not in FORMAT_EXTENSIONS:
        return {
            "success": False,
            "error": f"不支持的输出格式 '{output_format}'，可选: {', '.join(sorted(set(list(FORMAT_EXTENSIONS.keys()) + list(RASTER_FORMAT_EXTENSIONS.keys()))))}",
        }

    if not isinstance(layer, QgsVectorLayer):
        return {"success": False, "error": f"图层 '{layer_name}' 不是矢量图层，无法导出为 {fmt}"}

    driver_name = DRIVER_MAP.get(fmt)
    if not driver_name:
        return {"success": False, "error": f"格式 '{fmt}' 无对应的 OGR 驱动"}

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    if os.path.exists(output_path) and _confirm_callback:
        result = _confirm_callback(f"文件 '{output_path}' 已存在，是否覆盖？")
        if not result.confirmed:
            return {"success": False, "error": "用户取消覆盖"}

    res = _export_vector(layer, output_path, driver_name, target_crs, only_selected)

    if res["success"]:
        return {
            "success": True,
            "message": (
                f"已将 '{layer_name}' 导出为 {fmt.upper()} 格式，"
                f"共 {res['feature_count']} 个要素，保存到: {res['output_path']}"
            ),
            "results": [{
                "input": layer_name,
                "output_format": fmt,
                "output_path": res["output_path"],
                "feature_count": res["feature_count"],
                "layer_type": "vector",
            }],
        }
    else:
        return {"success": False, "error": res["error"]}
