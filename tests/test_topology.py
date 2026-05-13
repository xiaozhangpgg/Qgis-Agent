"""Tests for topology check and fix tools."""

import pytest
from unittest.mock import MagicMock, patch
from tools.topology_rules import (
    TOPOLOGY_RULES,
    resolve_rule_name,
    get_rules_for_geometry_type,
    get_cross_layer_rules,
    is_cross_layer_rule,
    FIX_STRATEGIES,
    AUTO_FIXABLE_TYPES,
)


class TestTopologyRules:
    """Test topology rules mapping."""

    def test_rule_count(self):
        """Test that all rules are defined."""
        assert len(TOPOLOGY_RULES) == 10

    def test_rule_tuple_structure(self):
        """Test that each rule has 5-element tuple (impl, error_type, desc, geom_type, cross_layer)."""
        for rule_name, value in TOPOLOGY_RULES.items():
            assert len(value) == 5, f"Rule '{rule_name}' should have 5 elements, got {len(value)}"
            impl, error_type, desc, geom_type, cross_layer = value
            assert isinstance(impl, str), f"Rule '{rule_name}' impl should be str"
            assert isinstance(error_type, str), f"Rule '{rule_name}' error_type should be str"
            assert isinstance(desc, str), f"Rule '{rule_name}' desc should be str"
            assert geom_type in ("point", "line", "polygon", "all"), f"Rule '{rule_name}' has invalid geom_type: {geom_type}"
            assert isinstance(cross_layer, bool), f"Rule '{rule_name}' cross_layer should be bool"

    def test_resolve_simplified_name(self):
        """Test resolving simplified rule names."""
        assert resolve_rule_name("no_overlaps") == "no_overlaps"
        assert resolve_rule_name("no_gaps") == "no_gaps"
        assert resolve_rule_name("invalid_geometry") == "invalid_geometry"

    def test_resolve_qgis_native_name(self):
        """Test resolving QGIS native rule names."""
        assert resolve_rule_name("QgsGeometryValidate.NoOverlaps") == "no_overlaps"
        assert resolve_rule_name("QgsGeometryValidate.NoGaps") == "no_gaps"
        assert resolve_rule_name("QgsGeometryValidate.NoDangles") == "no_dangles"
        assert resolve_rule_name("QgsGeometryValidate.NoSelfIntersections") == "no_self_intersections"
        assert resolve_rule_name("QgsGeometryValidate.NoPseudoNodes") == "no_pseudo_nodes"
        assert resolve_rule_name("QgsGeometryValidate.NoDuplicatePoints") == "no_duplicate_points"
        assert resolve_rule_name("QgsGeometryValidate.PointInPolygon") == "point_in_polygon"
        assert resolve_rule_name("QgsGeometryValidate.LineInPolygon") == "line_in_polygon"
        assert resolve_rule_name("QgsGeometryValidate.PolygonCoverage") == "polygon_coverage"
        assert resolve_rule_name("QgsGeometryValidate.InvalidGeometry") == "invalid_geometry"

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

    def test_cross_layer_rules(self):
        """Test cross-layer rule identification."""
        cross_rules = get_cross_layer_rules()
        assert "point_in_polygon" in cross_rules
        assert "line_in_polygon" in cross_rules
        assert "polygon_coverage" in cross_rules
        assert "no_overlaps" not in cross_rules
        assert "no_gaps" not in cross_rules

    def test_is_cross_layer_rule(self):
        """Test is_cross_layer_rule function."""
        assert is_cross_layer_rule("point_in_polygon") is True
        assert is_cross_layer_rule("line_in_polygon") is True
        assert is_cross_layer_rule("polygon_coverage") is True
        assert is_cross_layer_rule("no_overlaps") is False
        assert is_cross_layer_rule("invalid_geometry") is False
        assert is_cross_layer_rule("unknown_rule") is False

    def test_fix_strategies_complete(self):
        """Test that all error types have fix strategies."""
        for rule_name, (_, error_type, _, _, _) in TOPOLOGY_RULES.items():
            assert error_type in FIX_STRATEGIES, f"Missing fix strategy for {error_type}"

    def test_not_auto_fixable_types(self):
        """Test that cross-layer error types are marked as not auto-fixable."""
        not_fixable = ["point_outside_polygon", "line_outside_polygon", "polygon_not_covered"]
        for et in not_fixable:
            assert et in FIX_STRATEGIES, f"Missing fix strategy for {et}"
            assert FIX_STRATEGIES[et] == "not_auto_fixable", f"{et} should be not_auto_fixable"
            assert et not in AUTO_FIXABLE_TYPES, f"{et} should not be in AUTO_FIXABLE_TYPES"

    def test_auto_fixable_types(self):
        """Test that auto-fixable types exclude not_auto_fixable."""
        for et in AUTO_FIXABLE_TYPES:
            assert et in FIX_STRATEGIES
            assert FIX_STRATEGIES[et] != "not_auto_fixable"

    def test_fix_strategy_correctness(self):
        """Test that fix strategies use correct algorithm names."""
        assert FIX_STRATEGIES["dangle"] == "extend_to_nearest"
        assert FIX_STRATEGIES["pseudo_node"] == "merge_lines"
        assert FIX_STRATEGIES["overlap"] == "difference"
        assert FIX_STRATEGIES["gap"] == "buffer_dissolve"
        assert FIX_STRATEGIES["self_intersection"] == "fix_geometries"
        assert FIX_STRATEGIES["invalid_geometry"] == "fix_geometries"
        assert FIX_STRATEGIES["duplicate_point"] == "remove_duplicates"


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
    def test_unknown_error_type(self, mock_find_layer, mock_processing):
        """Test fix with unknown error type."""
        mock_layer = MagicMock()
        mock_layer.isValid.return_value = True
        mock_find_layer.return_value = mock_layer

        from tools.topology_fix import run_topology_fix
        result = run_topology_fix("test_layer", error_types=["invalid_type"])

        assert result["success"] is False
        assert "未知" in result["error"]

    @patch('tools.topology_fix.processing')
    @patch('tools.topology_fix._find_layer')
    def test_not_auto_fixable_error_type(self, mock_find_layer, mock_processing):
        """Test fix with not-auto-fixable error type."""
        mock_layer = MagicMock()
        mock_layer.isValid.return_value = True
        mock_find_layer.return_value = mock_layer

        from tools.topology_fix import run_topology_fix
        result = run_topology_fix("test_layer", error_types=["point_outside_polygon"])

        assert result["success"] is False
        assert "无法自动修复" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
