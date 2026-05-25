import os
from typing import Any, List, Optional, Tuple

from qgis.core import QgsProject, QgsMapLayer


def find_layer(name: str) -> Optional[QgsMapLayer]:
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None


def find_layer_with_warnings(name: str) -> Tuple[Any, List[str]]:
    project = QgsProject.instance()
    matches = []
    for layer in project.mapLayers().values():
        if layer.name() == name:
            matches.append(layer)

    warnings = []
    if len(matches) > 1:
        warnings.append(f"图层 '{name}' 存在 {len(matches)} 个同名实例，使用第一个")

    if matches:
        return matches[0], warnings
    return None, warnings


def find_layer_case_insensitive(name: str) -> Optional[QgsMapLayer]:
    project = QgsProject.instance()
    normalized = name.strip().lower()
    for layer in project.mapLayers().values():
        if layer.name().strip().lower() == normalized:
            return layer
    return None


def resolve_input(layer):
    source = layer.source()
    if source and not source.startswith("memory:"):
        file_path = source.split("|")[0]
        for prefix in ("ogr:", "gdal:"):
            if file_path.startswith(prefix):
                file_path = file_path[len(prefix):]
                break
        if os.path.exists(file_path):
            return source
    return layer


FORMAT_EXTENSIONS = {
    "geojson": "geojson",
    "gpkg": "gpkg",
    "kml": "kml",
    "csv": "csv",
    "shp": "shp",
    "gml": "gml",
    "dxf": "dxf",
    "xlsx": "xlsx",
}

DRIVER_MAP = {
    "geojson": "GeoJSON",
    "gpkg": "GPKG",
    "kml": "KML",
    "csv": "CSV",
    "shp": "ESRI Shapefile",
    "gml": "GML",
    "dxf": "DXF",
    "xlsx": "XLSX",
}


def resolve_output_name(project: QgsProject, base_name: str) -> str:
    existing = {layer.name() for layer in project.mapLayers().values()}
    if base_name not in existing:
        return base_name
    idx = 1
    while f"{base_name}_{idx}" in existing:
        idx += 1
    return f"{base_name}_{idx}"


RASTER_FORMAT_EXTENSIONS = {
    "geotiff": "tif",
    "tiff": "tif",
    "img": "img",
}

RASTER_DRIVER_MAP = {
    "geotiff": "GTiff",
    "tiff": "GTiff",
    "img": "HFA",
}


def is_raster_format(fmt: str) -> bool:
    return fmt.lower().strip().lstrip(".") in RASTER_FORMAT_EXTENSIONS
