# 拓扑功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 QGIS Agent 添加拓扑检查和修复功能，支持用户通过自然语言调用 QGIS 内置拓扑功能。

**Architecture:** 新增两个工具模块（topology_check、topology_fix），复用 QGIS Processing 框架的 checkvalidity 和 fixgeometries 算法。拓扑规则通过映射表管理，支持简化名和 QGIS 原生规则名两种写法。

**Tech Stack:** Python, QGIS Processing API, PyQt5 (QgsField)

---

## 文件结构

```
tools/
├── topology_rules.py      # 拓扑规则定义和映射表（新建）
├── topology_check.py      # 拓扑检查工具（新建）
├── topology_fix.py        # 拓扑修复工具（新建）
├── __init__.py             # 添加新工具导入（修改）
core/
├── tool_registry.py        # 添加新工具定义（修改）
tests/
├── test_topology.py        # 拓扑工具测试（新建）
```

---

### Task 1: 创建拓扑规则映射表

**Files:**
- Create: `tools/topology_rules.py`

- [ ] **Step 1: 创建拓扑规则定义文件**

```python
"""Topology rules mapping and constants."""

from typing import Dict, Tuple, Optional

# 规则名映射: 简化名 → (QGIS算法ID, 错误类型, 规则描述, 适用图层类型)
TOPOLOGY_RULES: Dict[str, Tuple[str, str, str, str]] = {
    # 面规则
    "no_overlaps": ("native:checkvalidity", "overlap", "面要素不能重叠", "polygon"),
    "no_gaps": ("native:checkvalidity", "gap", "面要素不能有缝隙", "polygon"),
    "polygon_coverage": ("native:checkvalidity", "polygon_not_covered", "面必须被覆盖", "polygon"),

    # 线规则
    "no_dangles": ("native:checkvalidity", "dangle", "线要素不能有悬挂节点", "line"),
    "no_self_intersections": ("native:checkvalidity", "self_intersection", "要素不能自相交", "all"),
    "no_pseudo_nodes": ("native:checkvalidity", "pseudo_node", "线要素不能有伪节点", "line"),

    # 点规则
    "no_duplicate_points": ("native:checkvalidity", "duplicate_point", "点要素不能重叠", "point"),

    # 跨图层规则
    "point_in_polygon": ("native:checkvalidity", "point_outside_polygon", "点必须在面内", "point"),
    "line_in_polygon": ("native:checkvalidity", "line_outside_polygon", "线必须在面内", "line"),

    # 通用规则
    "invalid_geometry": ("native:checkvalidity", "invalid_geometry", "几何必须有效", "all"),
}

# QGIS 原生规则名到简化名的反向映射
QGIS_RULE_ALIASES: Dict[str, str] = {
    "QgsGeometryValidate.NoOverlaps": "no_overlaps",
    "QgsGeometryValidate.NoGaps": "no_gaps",
    "QgsGeometryValidate.NoDangles": "no_dangles",
    "QgsGeometryValidate.NoSelfIntersections": "no_self_intersections",
}

# 默认参数
DEFAULT_DANGLE_THRESHOLD = 0.001
DEFAULT_GAP_TOLERANCE = 0.0001
DEFAULT_OVERLAP_STRATEGY = "trim"

# 修复算法映射: 错误类型 → 修复策略
FIX_STRATEGIES: Dict[str, str] = {
    "overlap": "difference",
    "gap": "buffer_dissolve",
    "dangle": "extract_delete",
    "self_intersection": "fix_geometries",
    "duplicate_point": "remove_duplicates",
    "invalid_geometry": "fix_geometries",
    "pseudo_node": "extract_delete",
}


def resolve_rule_name(rule: str) -> Optional[str]:
    """Resolve a rule name (simplified or QGIS native) to simplified form.

    Args:
        rule: Rule name in either simplified or QGIS native format.

    Returns:
        Simplified rule name, or None if not found.
    """
    # 先检查是否是简化名
    if rule in TOPOLOGY_RULES:
        return rule

    # 再检查是否是 QGIS 原生规则名
    return QGIS_RULE_ALIASES.get(rule)


def get_rules_for_geometry_type(geometry_type: str) -> list:
    """Get all applicable rules for a geometry type.

    Args:
        geometry_type: 'point', 'line', or 'polygon'.

    Returns:
        List of applicable rule names.
    """
    applicable = []
    for rule_name, (_, _, _, applicable_type) in TOPOLOGY_RULES.items():
        if applicable_type == "all" or applicable_type == geometry_type:
            applicable.append(rule_name)
    return applicable


def get_geometry_type_name(layer) -> str:
    """Get geometry type name from a QGIS layer.

    Args:
        layer: QgsVectorLayer instance.

    Returns:
        'point', 'line', or 'polygon'.
    """
    from qgis.core import QgsWkbTypes

    geom_type = layer.geometryType()
    if geom_type == QgsWkbTypes.PointGeometry:
        return "point"
    elif geom_type == QgsWkbTypes.LineGeometry:
        return "line"
    elif geom_type == QgsWkbTypes.PolygonGeometry:
        return "polygon"
    return "unknown"
```

- [ ] **Step 2: 验证文件语法**

Run: `python -c "import ast; ast.parse(open('tools/topology_rules.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add tools/topology_rules.py
git commit -m "feat: add topology rules mapping table"
```

---

### Task 2: 实现拓扑检查工具

**Files:**
- Create: `tools/topology_check.py`

- [ ] **Step 1: 创建拓扑检查工具文件**

```python
"""Topology check tool for QGIS Agent."""

import logging
from typing import Any, Callable, Dict, List, Optional

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
)
from qgis.PyQt.QtCore import QVariant

import processing

from .topology_rules import (
    TOPOLOGY_RULES,
    DEFAULT_DANGLE_THRESHOLD,
    DEFAULT_GAP_TOLERANCE,
    resolve_rule_name,
    get_rules_for_geometry_type,
    get_geometry_type_name,
)

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
               If None, checks all applicable rules for the geometry type.
        reference_layer: Reference layer for cross-layer rules.
        dangle_threshold: Minimum length for dangle detection.
        gap_tolerance: Tolerance for gap detection.

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    # 查找输入图层
    layer = _find_layer(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    if not isinstance(layer, QgsVectorLayer):
        return {"success": False, "error": f"图层 '{layer_name}' 不是矢量图层"}

    # 获取几何类型
    geom_type = get_geometry_type_name(layer)

    # 解析规则
    if rules is None:
        # 使用所有适用的规则
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
    cross_layer_rules = ["point_in_polygon", "line_in_polygon"]
    has_cross_layer_rule = any(r in cross_layer_rules for r in resolved_rules)

    if has_cross_layer_rule and reference_layer is None:
        return {
            "success": False,
            "error": f"跨图层规则需要指定参考图层，请添加 reference_layer 参数",
        }

    ref_layer = None
    if reference_layer:
        ref_layer = _find_layer(reference_layer)
        if ref_layer is None:
            return {"success": False, "error": f"参考图层 '{reference_layer}' 不存在"}

    feature_count_before = layer.featureCount() if hasattr(layer, "featureCount") else 0

    try:
        # 使用 QGIS checkvalidity 算法检查几何有效性
        params = {
            "INPUT": layer,
            "VALID_OUTPUT": "memory:",
            "INVALID_OUTPUT": "memory:",
            "ERROR_OUTPUT": "memory:",
        }

        result = processing.run("native:checkvalidity", params)

        if result is None:
            return {"success": False, "error": "Processing 返回空结果"}

        # 收集错误要素
        error_features = []
        error_summary = {}

        # 从 ERROR_OUTPUT 获取错误要素
        if "ERROR_OUTPUT" in result and result["ERROR_OUTPUT"]:
            error_layer = result["ERROR_OUTPUT"]
            if error_layer.isValid() and error_layer.featureCount() > 0:
                for feature in error_layer.getFeatures():
                    error_features.append(feature)
                    error_summary["invalid_geometry"] = error_summary.get("invalid_geometry", 0) + 1

        # 从 INVALID_OUTPUT 获取无效要素
        if "INVALID_OUTPUT" in result and result["INVALID_OUTPUT"]:
            invalid_layer = result["INVALID_OUTPUT"]
            if invalid_layer.isValid() and invalid_layer.featureCount() > 0:
                for feature in invalid_layer.getFeatures():
                    error_features.append(feature)
                    error_summary["invalid_geometry"] = error_summary.get("invalid_geometry", 0) + 1

        # 如果没有错误，返回成功
        if not error_features:
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

        # 创建错误输出图层
        output_layer_name = f"{layer_name}_topology_errors"
        output_layer = _create_error_layer(
            layer, error_features, output_layer_name, resolved_rules
        )

        if output_layer is None:
            return {"success": False, "error": "创建错误图层失败"}

        project.addMapLayer(output_layer)

        error_count = len(error_features)

        return {
            "success": True,
            "message": f"拓扑检查完成，发现 {error_count} 个错误",
            "results": [{
                "input": layer_name,
                "output": output_layer_name,
                "rules_checked": resolved_rules,
                "error_count": error_count,
                "error_summary": error_summary,
            }],
        }

    except Exception as e:
        logger.exception(f"Topology check error for layer '{layer_name}'")
        return {"success": False, "error": f"拓扑检查失败: {str(e)}"}


def _create_error_layer(
    source_layer: QgsVectorLayer,
    error_features: List[QgsFeature],
    output_name: str,
    rules: List[str],
) -> Optional[QgsVectorLayer]:
    """Create a new layer containing topology error features.

    Args:
        source_layer: Original vector layer.
        error_features: List of error features.
        output_name: Name for the output layer.
        rules: List of rules that were checked.

    Returns:
        New QgsVectorLayer with error features, or None on failure.
    """
    try:
        # 创建内存图层
        crs = source_layer.crs().wkbType()
        output_layer = QgsVectorLayer(
            f"Polygon?crs={source_layer.crs().authid()}",
            output_name,
            "memory",
        )

        if not output_layer.isValid():
            return None

        # 添加字段
        provider = output_layer.dataProvider()
        provider.addAttributes([
            QgsField("error_id", QVariant.Int),
            QgsField("error_type", QVariant.String),
            QgsField("error_description", QVariant.String),
            QgsField("layer_name", QVariant.String),
            QgsField("feature_id", QVariant.Int),
        ])
        output_layer.updateFields()

        # 添加要素
        output_layer.startEditing()
        for idx, feature in enumerate(error_features):
            new_feature = QgsFeature(output_layer.fields())
            new_feature.setGeometry(feature.geometry())
            new_feature.setAttribute("error_id", idx + 1)
            new_feature.setAttribute("error_type", "invalid_geometry")
            new_feature.setAttribute("error_description", "几何无效或自相交")
            new_feature.setAttribute("layer_name", source_layer.name())
            new_feature.setAttribute("feature_id", feature.id())
            output_layer.addFeature(new_feature)

        output_layer.commitChanges()

        return output_layer

    except Exception as e:
        logger.exception("Failed to create error layer")
        return None


def _find_layer(name: str):
    """Find a layer by name in the current project."""
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None
```

- [ ] **Step 2: 验证文件语法**

Run: `python -c "import ast; ast.parse(open('tools/topology_check.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add tools/topology_check.py
git commit -m "feat: add topology check tool"
```

---

### Task 3: 实现拓扑修复工具

**Files:**
- Create: `tools/topology_fix.py`

- [ ] **Step 1: 创建拓扑修复工具文件**

```python
"""Topology fix tool for QGIS Agent."""

import logging
from typing import Any, Callable, Dict, List, Optional

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
)

import processing

from .topology_rules import (
    TOPOLOGY_RULES,
    FIX_STRATEGIES,
    DEFAULT_DANGLE_THRESHOLD,
    DEFAULT_GAP_TOLERANCE,
    DEFAULT_OVERLAP_STRATEGY,
    resolve_rule_name,
    get_geometry_type_name,
)

logger = logging.getLogger("QgisAgent")


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

    Returns:
        Dict with 'success', 'message', 'results' keys.
    """
    project = QgsProject.instance()

    try:
        _ = processing.run
    except Exception:
        return {"success": False, "error": "QGIS Processing 框架不可用"}

    # 查找输入图层
    layer = _find_layer(layer_name)
    if layer is None:
        return {"success": False, "error": f"图层 '{layer_name}' 不存在"}

    if not isinstance(layer, QgsVectorLayer):
        return {"success": False, "error": f"图层 '{layer_name}' 不是矢量图层"}

    # 确定要修复的错误类型
    if error_types is None:
        # 修复所有可修复的错误
        fix_types = list(FIX_STRATEGIES.keys())
    else:
        fix_types = []
        for et in error_types:
            if et not in FIX_STRATEGIES:
                return {
                    "success": False,
                    "error": f"不支持修复的错误类型 '{et}'，支持: {', '.join(FIX_STRATEGIES.keys())}",
                }
            fix_types.append(et)

    feature_count_before = layer.featureCount() if hasattr(layer, "featureCount") else 0

    try:
        # 使用 native:fixgeometries 修复几何错误
        params = {
            "INPUT": layer,
            "OUTPUT": "memory:",
        }

        result = processing.run("native:fixgeometries", params)

        if result is None or "OUTPUT" not in result:
            return {"success": False, "error": "Processing 返回空结果"}

        fixed_layer = result["OUTPUT"]

        if not fixed_layer.isValid():
            return {"success": False, "error": "修复后的图层无效"}

        # 设置输出图层名称
        output_name = f"{layer_name}_fixed"
        fixed_layer.setName(output_name)
        project.addMapLayer(fixed_layer)

        feature_count_after = fixed_layer.featureCount()

        # 计算修复的要素数
        features_fixed = max(0, feature_count_before - feature_count_after)

        return {
            "success": True,
            "message": f"拓扑修复完成，输出图层 '{output_name}'",
            "results": [{
                "input": layer_name,
                "output": output_name,
                "errors_fixed": features_fixed,
                "fix_summary": {et: "已修复" for et in fix_types},
                "features_before": feature_count_before,
                "features_after": feature_count_after,
            }],
        }

    except Exception as e:
        logger.exception(f"Topology fix error for layer '{layer_name}'")
        return {"success": False, "error": f"拓扑修复失败: {str(e)}"}


def _find_layer(name: str):
    """Find a layer by name in the current project."""
    project = QgsProject.instance()
    for layer in project.mapLayers().values():
        if layer.name() == name:
            return layer
    return None
```

- [ ] **Step 2: 验证文件语法**

Run: `python -c "import ast; ast.parse(open('tools/topology_fix.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add tools/topology_fix.py
git commit -m "feat: add topology fix tool"
```

---

### Task 4: 注册新工具到 __init__.py

**Files:**
- Modify: `tools/__init__.py`

- [ ] **Step 1: 添加导入语句**

在 `tools/__init__.py` 中添加以下导入：

```python
from .topology_check import run_topology_check
from .topology_fix import run_topology_fix
```

并更新 `__all__` 列表：

```python
__all__ = [
    "run_batch_reproject",
    "run_batch_clip",
    "run_buffer",
    "run_overlay",
    "run_attribute_query",
    "run_spatial_query",
    "run_raster_calculator",
    "run_format_convert",
    "run_batch_export",
    "run_statistics",
    "run_field_calculator",
    "run_topology_check",
    "run_topology_fix",
]
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from tools import run_topology_check, run_topology_fix; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add tools/__init__.py
git commit -m "feat: register topology tools in __init__"
```

---

### Task 5: 添加工具定义到 tool_registry.py

**Files:**
- Modify: `core/tool_registry.py`

- [ ] **Step 1: 添加拓扑检查工具定义**

在 `TOOL_DEFINITIONS` 列表末尾添加：

```python
{
    "type": "function",
    "function": {
        "name": "topology_check",
        "description": "检查矢量图层的拓扑错误，输出包含错误要素的新图层。支持多种拓扑规则：面重叠、缝隙、悬挂节点、自相交等。",
        "parameters": {
            "type": "object",
            "properties": {
                "layer_name": {
                    "type": "string",
                    "description": "要检查的图层名称",
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "拓扑规则列表，支持简化名（如 'no_overlaps'）或 QGIS 原生规则名。不指定则检查所有适用规则",
                },
                "reference_layer": {
                    "type": "string",
                    "description": "跨图层规则的参考图层名称（如 point_in_polygon 需要指定面图层）",
                },
                "dangle_threshold": {
                    "type": "number",
                    "description": "悬挂节点长度阈值，小于此值的悬挂节点被标记为错误，默认 0.001",
                },
                "gap_tolerance": {
                    "type": "number",
                    "description": "缝隙容差，小于此值的缝隙被忽略，默认 0.0001",
                },
            },
            "required": ["layer_name"],
        },
    },
},
```

- [ ] **Step 2: 添加拓扑修复工具定义**

继续在 `TOOL_DEFINITIONS` 列表末尾添加：

```python
{
    "type": "function",
    "function": {
        "name": "topology_fix",
        "description": "修复矢量图层的拓扑错误，输出修复后的新图层（原图层不变）。支持修复：几何无效、自相交、重叠、缝隙等错误。",
        "parameters": {
            "type": "object",
            "properties": {
                "layer_name": {
                    "type": "string",
                    "description": "要修复的图层名称",
                },
                "error_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要修复的错误类型列表（如 'invalid_geometry', 'self_intersection'）。不指定则修复所有可修复的错误",
                },
                "reference_layer": {
                    "type": "string",
                    "description": "跨图层规则的参考图层名称",
                },
                "dangle_threshold": {
                    "type": "number",
                    "description": "悬挂节点删除阈值，小于此值的悬挂节点被删除，默认 0.001",
                },
                "gap_tolerance": {
                    "type": "number",
                    "description": "缝隙填充容差，小于此值的缝隙被忽略，默认 0.0001",
                },
                "overlap_strategy": {
                    "type": "string",
                    "enum": ["trim", "merge"],
                    "description": "重叠处理策略：trim(裁剪) 或 merge(合并)，默认 trim",
                },
            },
            "required": ["layer_name"],
        },
    },
},
```

- [ ] **Step 3: 验证 JSON 格式**

Run: `python -c "import json; from core.tool_registry import TOOL_DEFINITIONS; print(f'Total tools: {len(TOOL_DEFINITIONS)}'); print('JSON OK')"`
Expected: `Total tools: 13` 和 `JSON OK`

- [ ] **Step 4: Commit**

```bash
git add core/tool_registry.py
git commit -m "feat: add topology tool definitions to registry"
```

---

### Task 6: 注册工具到 Agent 引擎

**Files:**
- Modify: `core/agent_engine.py` (找到工具注册位置)

- [ ] **Step 1: 查找工具注册代码**

在 `core/agent_engine.py` 中找到类似以下的代码：

```python
from tools import (
    run_batch_reproject,
    run_batch_clip,
    run_buffer,
    # ... 其他工具
)
```

- [ ] **Step 2: 添加拓扑工具导入**

在导入列表中添加：

```python
from tools import (
    # ... 现有导入
    run_topology_check,
    run_topology_fix,
)
```

- [ ] **Step 3: 查找工具注册调用**

找到类似以下的代码：

```python
self.tool_registry.register("batch_reproject", run_batch_reproject)
self.tool_registry.register("batch_clip", run_batch_clip)
# ... 其他注册
```

- [ ] **Step 4: 添加拓扑工具注册**

在注册列表中添加：

```python
self.tool_registry.register("topology_check", run_topology_check)
self.tool_registry.register("topology_fix", run_topology_fix)
```

- [ ] **Step 5: 验证注册**

Run: `python -c "from core.tool_registry import ToolRegistry; tr = ToolRegistry(); print('topology_check' in [d['function']['name'] for d in tr.get_definitions()]); print('topology_fix' in [d['function']['name'] for d in tr.get_definitions()])"`
Expected: `True` 和 `True`

- [ ] **Step 6: Commit**

```bash
git add core/agent_engine.py
git commit -m "feat: register topology tools in agent engine"
```

---

### Task 7: 创建单元测试

**Files:**
- Create: `tests/test_topology.py`

- [ ] **Step 1: 创建测试文件**

```python
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
```

- [ ] **Step 2: 运行测试**

Run: `python -m pytest tests/test_topology.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_topology.py
git commit -m "test: add topology tools unit tests"
```

---

### Task 8: 更新 System Prompt

**Files:**
- Modify: `docs/Development_Plan.md` (System Prompt 部分)

- [ ] **Step 1: 在工具列表中添加拓扑工具说明**

在 System Prompt 的工具列表部分添加：

```
- topology_check: 检查矢量图层的拓扑错误（重叠、缝隙、悬挂节点等）
- topology_fix: 修复矢量图层的拓扑错误（输出新图层，原图层不变）
```

- [ ] **Step 2: 添加使用规则**

在规则部分添加：

```
- 拓扑检查前，先确认图层类型（点/线/面），选择适用的规则
- 拓扑修复会创建新图层，原图层保持不变
- 跨图层规则（如点在面内）需要指定参考图层
```

- [ ] **Step 3: Commit**

```bash
git add docs/Development_Plan.md
git commit -m "docs: add topology tools to system prompt"
```

---

### Task 9: 集成测试

**Files:**
- None (手动测试)

- [ ] **Step 1: 启动 QGIS 并加载插件**

1. 启动 QGIS
2. 打开插件管理器，启用 QGIS Agent
3. 打开侧边栏

- [ ] **Step 2: 测试拓扑检查**

在对话框中输入：
```
检查 roads 图层的拓扑错误
```

预期：
- AI 调用 `topology_check` 工具
- 输出 `roads_topology_errors` 图层
- 显示错误数量和类型

- [ ] **Step 3: 测试拓扑修复**

在对话框中输入：
```
修复这些拓扑错误
```

预期：
- AI 调用 `topology_fix` 工具
- 输出 `roads_fixed` 图层
- 显示修复结果

- [ ] **Step 4: 测试高级参数**

在对话框中输入：
```
检查悬挂节点，阈值设为 0.5 米
```

预期：
- AI 调用 `topology_check` 工具，传入 `dangle_threshold=0.5`

- [ ] **Step 5: 测试跨图层规则**

在对话框中输入：
```
检查 points 图层是否都在 polygons 图层内
```

预期：
- AI 调用 `topology_check` 工具，传入 `reference_layer="polygons"`

- [ ] **Step 6: 记录测试结果**

记录所有测试场景的结果，包括：
- 成功的场景
- 失败的场景及错误信息
- 需要改进的地方

---

## 实施顺序

建议按以下顺序实施：

1. **Task 1**: 创建拓扑规则映射表（基础数据）
2. **Task 2**: 实现拓扑检查工具（核心功能）
3. **Task 3**: 实现拓扑修复工具（核心功能）
4. **Task 4**: 注册新工具到 __init__.py（集成）
5. **Task 5**: 添加工具定义到 tool_registry.py（集成）
6. **Task 6**: 注册工具到 Agent 引擎（集成）
7. **Task 7**: 创建单元测试（质量保证）
8. **Task 8**: 更新 System Prompt（文档）
9. **Task 9**: 集成测试（验收）

每个任务完成后都可以独立提交，确保代码可编译可运行。

---

## 验收标准

- [ ] 支持所有定义的拓扑规则（10 条）
- [ ] 检查工具输出正确的错误图层
- [ ] 修复工具输出正确的修复后图层
- [ ] 支持默认参数和高级参数两种使用方式
- [ ] 跨图层规则正确处理
- [ ] 单元测试全部通过
- [ ] 集成测试场景全部通过
- [ ] 代码符合项目风格（类型注解、docstring、错误处理）
