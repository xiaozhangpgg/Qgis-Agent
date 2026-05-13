"""Tests for topology check and fix tools."""

import pytest
from unittest.mock import MagicMock, patch
from tools.topology_rules import (
    TOPOLOGY_RULES,
    resolve_rule_name,
    get_rules_for_geometry_type,
    FIX_STRATEGIES,
)


class TestTopologyRules:
    """Test topology rules mapping."""

    def test_rule_count(self):
        """Test that all rules are defined."""
        assert len(TOPOLOGY_RULES) == 10

    def test_resolve_simplified_name(self):
        """Test resolving simplified rule names."""
        assert resolve_rule_name("no_overlaps") == "no_overlaps"
        assert resolve_rule_name("no_gaps") == "no_gaps"
        assert resolve_rule_name("invalid_geometry") == "invalid_geometry"

    def test_resolve_qgis_native_name(self):
        """Test resolving QGIS native rule names."""
        assert resolve_rule_name("QgsGeometryValidate.NoOverlaps") == "no_overlaps"
        assert resolve_rule_name("QgsGeometryValidate.NoGaps") == "no_gaps"

    def test_resolve_unknown_rule(self):
        """Test resolving unknown rule returns None."""
        assert resolve_rule_name("unknown_rule") is None
        assert resolve_rule_name("") is None

    def test_get_rules_for_point(self):
        """Test getting rules for point geometry."""
        rules = get_rules_for_geometry_type("point")
        assert "no_duplicate_points" in rules
        assert "point_in_polygon" in rules
        assert "invalid_geometry" in rules
        assert "no_dangles" not in rules

    def test_get_rules_for_line(self):
        """Test getting rules for line geometry."""
        rules = get_rules_for_geometry_type("line")
        assert "no_dangles" in rules
        assert "no_self_intersections" in rules
        assert "no_pseudo_nodes" in rules
        assert "no_overlaps" not in rules

    def test_get_rules_for_polygon(self):
        """Test getting rules for polygon geometry."""
        rules = get_rules_for_geometry_type("polygon")
        assert "no_overlaps" in rules
        assert "no_gaps" in rules
        assert "polygon_coverage" in rules
        assert "no_dangles" not in rules

    def test_fix_strategies_complete(self):
        """Test that all error types have fix strategies."""
        for rule_name, (_, error_type, _, _) in TOPOLOGY_RULES.items():
            if error_type not in ["point_outside_polygon", "line_outside_polygon", "polygon_not_covered"]:
                assert error_type in FIX_STRATEGIES, f"Missing fix strategy for {error_type}"


class TestTopologyCheck:
    """Test topology check tool."""

    @patch('tools.topology_check.processing')
    @patch('tools.topology_check._find_layer')
    def test_layer_not_found(self, mock_find_layer, mock_processing):
        """Test check with non-existent layer."""
        mock_find_layer.return_value = None

        from tools.topology_check import run_topology_check
        result = run_topology_check("nonexistent_layer")

        assert result["success"] is False
        assert "不存在" in result["error"]

    @patch('tools.topology_check.processing')
    @patch('tools.topology_check._find_layer')
    def test_invalid_rule(self, mock_find_layer, mock_processing):
        """Test check with invalid rule name."""
        mock_layer = MagicMock()
        mock_layer.isValid.return_value = True
        mock_find_layer.return_value = mock_layer

        from tools.topology_check import run_topology_check
        result = run_topology_check("test_layer", rules=["invalid_rule"])

        assert result["success"] is False
        assert "不支持" in result["error"]

    @patch('tools.topology_check.processing')
    @patch('tools.topology_check._find_layer')
    def test_cross_layer_rule_without_reference(self, mock_find_layer, mock_processing):
        """Test cross-layer rule without reference layer."""
        mock_layer = MagicMock()
        mock_layer.isValid.return_value = True
        mock_layer.geometryType.return_value = 0  # Point
        mock_find_layer.return_value = mock_layer

        from tools.topology_check import run_topology_check
        result = run_topology_check("test_layer", rules=["point_in_polygon"])

        assert result["success"] is False
        assert "参考图层" in result["error"]


class TestTopologyFix:
    """Test topology fix tool."""

    @patch('tools.topology_fix.processing')
    @patch('tools.topology_fix._find_layer')
    def test_layer_not_found(self, mock_find_layer, mock_processing):
        """Test fix with non-existent layer."""
        mock_find_layer.return_value = None

        from tools.topology_fix import run_topology_fix
        result = run_topology_fix("nonexistent_layer")

        assert result["success"] is False
        assert "不存在" in result["error"]

    @patch('tools.topology_fix.processing')
    @patch('tools.topology_fix._find_layer')
    def test_invalid_error_type(self, mock_find_layer, mock_processing):
        """Test fix with invalid error type."""
        mock_layer = MagicMock()
        mock_layer.isValid.return_value = True
        mock_find_layer.return_value = mock_layer

        from tools.topology_fix import run_topology_fix
        result = run_topology_fix("test_layer", error_types=["invalid_type"])

        assert result["success"] is False
        assert "不支持" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
