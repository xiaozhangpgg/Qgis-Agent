import json
import logging
from typing import Any, Dict, List, Optional

from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsVectorLayer,
    QgsRasterLayer,
)

logger = logging.getLogger("QgisAgent")


class ContextManager:
    """Collects QGIS project context for LLM system prompt injection."""

    def __init__(self, iface):
        self.iface = iface

    def collect_context(self, source_filter: Optional[str] = None) -> Dict[str, Any]:
        """Collect current project context.

        Args:
            source_filter: If provided, only include layers matching this source
                          ("project" or "plugin"). None means include all.
        """
        project = QgsProject.instance()
        layers = self._collect_layers(project, source_filter)
        project_crs = project.crs().authid()
        selected_layers = self._get_selected_layer_names()

        return {
            "layers": layers,
            "project_crs": project_crs,
            "selected_layers": selected_layers,
            "layer_count": len(layers),
        }

    def collect_context_json(self, source_filter: Optional[str] = None) -> str:
        """Collect context and return as formatted JSON string."""
        ctx = self.collect_context(source_filter)
        return json.dumps(ctx, ensure_ascii=False, indent=2)

    def get_layer_names(self, source_filter: Optional[str] = None) -> List[str]:
        """Get list of all layer names in current project."""
        project = QgsProject.instance()
        names = []
        for layer in project.mapLayers().values():
            if source_filter:
                source = layer.customProperty("qgis_agent_source", "project")
                if source != source_filter:
                    continue
            names.append(layer.name())
        return names

    def get_layer_by_name(self, name: str) -> Optional[QgsMapLayer]:
        """Find a layer by name in the current project."""
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if layer.name() == name:
                return layer
        return None

    def validate_layer_exists(self, name: str) -> bool:
        """Check if a layer with the given name exists in the project."""
        return self.get_layer_by_name(name) is not None

    def validate_crs(self, crs_str: str) -> bool:
        """Check if a CRS string is valid (e.g., 'EPSG:4326')."""
        from qgis.core import QgsCoordinateReferenceSystem
        crs = QgsCoordinateReferenceSystem(crs_str)
        return crs.isValid()

    def _collect_layers(self, project: QgsProject,
                        source_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        result = []
        for layer in project.mapLayers().values():
            if source_filter:
                source = layer.customProperty("qgis_agent_source", "project")
                if source != source_filter:
                    continue

            info = self._layer_info(layer)
            if info:
                result.append(info)
        return result

    def _layer_info(self, layer: QgsMapLayer) -> Optional[Dict[str, Any]]:
        try:
            name = layer.name()
            source = layer.customProperty("qgis_agent_source", "project")

            if isinstance(layer, QgsVectorLayer):
                fields = [f.name() for f in layer.fields()]
                geom_type = layer.geometryType()
                geom_types = {
                    0: "Point",
                    1: "LineString",
                    2: "Polygon",
                    3: "UnknownGeometry",
                    4: "NoGeometry",
                }
                return {
                    "name": name,
                    "type": "vector",
                    "crs": layer.crs().authid(),
                    "geometry_type": geom_types.get(geom_type, "Unknown"),
                    "feature_count": layer.featureCount(),
                    "fields": fields,
                    "source": source,
                }
            elif isinstance(layer, QgsRasterLayer):
                return {
                    "name": name,
                    "type": "raster",
                    "crs": layer.crs().authid(),
                    "band_count": layer.bandCount(),
                    "source": source,
                }
            else:
                return {
                    "name": name,
                    "type": "unknown",
                    "source": source,
                }
        except Exception as e:
            logger.warning(f"Failed to collect info for layer '{layer.name()}': {e}")
            return None

    def _get_selected_layer_names(self) -> List[str]:
        try:
            canvas = self.iface.mapCanvas()
            selected = canvas.layers()
            return [l.name() for l in selected if l]
        except Exception:
            return []
