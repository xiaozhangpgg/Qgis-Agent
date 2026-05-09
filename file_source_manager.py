import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsMapLayer,
)
from qgis.PyQt.QtCore import QObject, pyqtSignal

logger = logging.getLogger("QgisAgent")

SUPPORTED_VECTOR_EXTS = {".shp", ".geojson", ".gpkg", ".kml", ".tab"}
SUPPORTED_RASTER_EXTS = {".tif", ".tiff", ".img", ".asc"}


class LayerSource(Enum):
    PROJECT = "project"
    PLUGIN = "plugin"


class SourceDecision(Enum):
    NO_LAYERS = "no_layers"
    ASK_USER = "ask_user"
    USE_PROJECT = "use_project"
    USE_PLUGIN = "use_plugin"


@dataclass
class ManagedFile:
    file_path: str
    display_name: str
    layer_name: str
    source: LayerSource = LayerSource.PLUGIN
    is_loaded: bool = False
    load_error: Optional[str] = None
    layer_id: Optional[str] = None


class FileSourceManager(QObject):
    """Manages plugin-imported files and temporary QGIS layers."""

    files_changed = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._files: Dict[str, ManagedFile] = {}

        project = QgsProject.instance()
        project.layersRemoved.connect(self._on_layers_removed)

    def add_file(self, file_path: str) -> Optional[ManagedFile]:
        if not os.path.isfile(file_path):
            return None

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_VECTOR_EXTS | SUPPORTED_RASTER_EXTS:
            return None

        display_name = os.path.basename(file_path)
        if display_name in self._files:
            return self._files[display_name]

        layer_name = self._unique_layer_name(display_name)
        managed = ManagedFile(
            file_path=file_path,
            display_name=display_name,
            layer_name=layer_name,
        )
        self._files[display_name] = managed
        self.files_changed.emit()
        return managed

    def remove_file(self, display_name: str):
        managed = self._files.pop(display_name, None)
        if managed and managed.is_loaded and managed.layer_id:
            self._unload_layer(managed.layer_id)
        self.files_changed.emit()

    def clear_all(self):
        for managed in list(self._files.values()):
            if managed.is_loaded and managed.layer_id:
                self._unload_layer(managed.layer_id)
        self._files.clear()
        self.files_changed.emit()

    def get_files(self) -> List[ManagedFile]:
        return list(self._files.values())

    def has_files(self) -> bool:
        return bool(self._files)

    def has_project_layers(self) -> bool:
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            source = layer.customProperty("qgis_agent_source", "project")
            if source == "project":
                return True
        return False

    def load_all_to_qgis(self) -> List[str]:
        loaded_names = []
        for managed in self._files.values():
            if managed.is_loaded:
                loaded_names.append(managed.layer_name)
                continue

            layer = self._load_file_as_layer(managed)
            if layer:
                managed.is_loaded = True
                managed.layer_id = layer.id()
                managed.load_error = None
                loaded_names.append(managed.layer_name)
            else:
                managed.load_error = "加载失败"
        return loaded_names

    def resolve_source(self) -> SourceDecision:
        has_project = self.has_project_layers()
        has_plugin = self.has_files()

        if not has_project and not has_plugin:
            return SourceDecision.NO_LAYERS
        if has_project and has_plugin:
            return SourceDecision.ASK_USER
        if has_project:
            return SourceDecision.USE_PROJECT
        return SourceDecision.USE_PLUGIN

    def get_source_description(self) -> str:
        decision = self.resolve_source()
        if decision == SourceDecision.NO_LAYERS:
            return "当前项目无可用图层，请在 QGIS 中加载图层或点击📎按钮添加文件。"
        if decision == SourceDecision.USE_PROJECT:
            return "使用当前项目中的图层。"
        if decision == SourceDecision.USE_PLUGIN:
            names = [f.layer_name for f in self._files.values()]
            return f"使用插件导入的文件: {', '.join(names)}"
        project_names = []
        plugin_names = []
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            source = layer.customProperty("qgis_agent_source", "project")
            if source == "project":
                project_names.append(layer.name())
            elif source == "plugin":
                plugin_names.append(layer.name())
        return (
            f"检测到两种数据来源：项目中有 {', '.join(project_names)}，"
            f"您导入了 {', '.join(plugin_names)}。请问使用哪种？"
        )

    def _load_file_as_layer(self, managed: ManagedFile) -> Optional[QgsMapLayer]:
        ext = os.path.splitext(managed.file_path)[1].lower()
        project = QgsProject.instance()

        if ext in SUPPORTED_VECTOR_EXTS:
            layer = QgsVectorLayer(managed.file_path, managed.layer_name, "ogr")
            if not layer.isValid():
                logger.warning(f"Invalid vector layer: {managed.file_path}")
                return None
            layer.setCustomProperty("qgis_agent_source", "plugin")
            project.addMapLayer(layer)
            return layer

        if ext in SUPPORTED_RASTER_EXTS:
            layer = QgsRasterLayer(managed.file_path, managed.layer_name, "gdal")
            if not layer.isValid():
                logger.warning(f"Invalid raster layer: {managed.file_path}")
                return None
            layer.setCustomProperty("qgis_agent_source", "plugin")
            project.addMapLayer(layer)
            return layer

        return None

    def _unload_layer(self, layer_id: str):
        project = QgsProject.instance()
        project.removeMapLayer(layer_id)

    def _unique_layer_name(self, display_name: str) -> str:
        base = os.path.splitext(display_name)[0]
        name = f"[plugin] {base}"
        project = QgsProject.instance()
        existing = {l.name() for l in project.mapLayers().values()}
        if name not in existing:
            return name
        counter = 2
        while f"[plugin] {base} ({counter})" in existing:
            counter += 1
        return f"[plugin] {base} ({counter})"

    def _on_layers_removed(self, layer_ids: list):
        changed = False
        for managed in self._files.values():
            if managed.is_loaded and managed.layer_id in layer_ids:
                managed.is_loaded = False
                managed.layer_id = None
                changed = True
        if changed:
            self.files_changed.emit()
