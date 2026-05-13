# 拓扑功能设计文档

**日期：** 2026-05-13
**版本：** 1.0
**状态：** 设计完成

---

## 1. 概述

### 1.1 背景

QGIS Agent 目前已实现 11 个 GIS 工具，涵盖坐标转换、裁剪、缓冲区、叠加分析等功能。但缺少拓扑检查和修复能力，用户需要手动使用 QGIS 拓扑检查器完成相关操作。

### 1.2 目标

为 QGIS Agent 添加拓扑检查和修复功能，支持用户通过自然语言描述需求，AI 自动调用 QGIS 内置拓扑功能完成操作。

### 1.3 设计原则

- **封装 QGIS 原生功能**：不重复实现拓扑算法，调用 QGIS Processing 框架
- **分离职责**：检查和修复分为独立工具，符合单一职责原则
- **安全优先**：修复操作输出新图层，不修改原图层
- **灵活配置**：支持默认值和高级参数两种使用方式

---

## 2. 拓扑规则定义

### 2.1 规则映射表

支持两种规则写法：简化名（推荐）和 QGIS 原生规则名。

```python
TOPOLOGY_RULES = {
    # 简化名 → (QGIS算法, 规则描述, 错误类型)
    "no_overlaps": ("qgis:checkvalidity", "面要素不能重叠", "overlap"),
    "no_gaps": ("qgis:checkvalidity", "面要素不能有缝隙", "gap"),
    "no_dangles": ("qgis:checkvalidity", "线要素不能有悬挂节点", "dangle"),
    "no_self_intersections": ("qgis:checkvalidity", "要素不能自相交", "self_intersection"),
    "no_pseudo_nodes": ("qgis:checkvalidity", "线要素不能有伪节点", "pseudo_node"),
    "no_duplicate_points": ("qgis:checkvalidity", "点要素不能重叠", "duplicate_point"),
    "point_in_polygon": ("qgis:checkvalidity", "点必须在面内", "point_outside_polygon"),
    "line_in_polygon": ("qgis:checkvalidity", "线必须在面内", "line_outside_polygon"),
    "polygon_coverage": ("qgis:checkvalidity", "面必须被覆盖", "polygon_not_covered"),
    "invalid_geometry": ("qgis:checkvalidity", "几何必须有效", "invalid_geometry"),
}
```

### 2.2 规则分类

| 类别 | 规则 | 适用图层类型 | 跨图层 |
|------|------|--------------|--------|
| 面规则 | no_overlaps, no_gaps, polygon_coverage | 面 | 否 |
| 线规则 | no_dangles, no_self_intersections, no_pseudo_nodes | 线 | 否 |
| 点规则 | no_duplicate_points | 点 | 否 |
| 跨图层 | point_in_polygon, line_in_polygon | 点/线 + 面 | 是 |
| 通用 | invalid_geometry | 所有 | 否 |

---

## 3. 工具设计

### 3.1 topology_check 工具

**功能：** 检查图层的拓扑错误，输出错误要素图层。

**LLM 函数定义：**

```json
{
    "type": "function",
    "function": {
        "name": "topology_check",
        "description": "检查矢量图层的拓扑错误，输出包含错误要素的新图层。",
        "parameters": {
            "type": "object",
            "properties": {
                "layer_name": {
                    "type": "string",
                    "description": "要检查的图层名称"
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "拓扑规则列表，支持简化名（如 'no_overlaps'）或 QGIS 原生规则名。不指定则检查所有适用规则"
                },
                "reference_layer": {
                    "type": "string",
                    "description": "跨图层规则的参考图层名称（如 point_in_polygon 需要指定面图层）"
                },
                "dangle_threshold": {
                    "type": "number",
                    "description": "悬挂节点长度阈值，小于此值的悬挂节点被标记为错误，默认 0.001"
                },
                "gap_tolerance": {
                    "type": "number",
                    "description": "缝隙容差，小于此值的缝隙被忽略，默认 0.0001"
                }
            },
            "required": ["layer_name"]
        }
    }
}
```

**输出：**
- 新图层：`<原图层名>_topology_errors`
- 字段：`error_id`, `error_type`, `error_description`, `layer_name`, `feature_id`

**返回值：**
```python
{
    "success": True,
    "message": "拓扑检查完成，发现 15 个错误",
    "results": [{
        "input": "roads",
        "output": "roads_topology_errors",
        "rules_checked": ["no_dangles", "no_self_intersections"],
        "error_count": 15,
        "error_summary": {
            "dangle": 10,
            "self_intersection": 5
        }
    }]
}
```

### 3.2 topology_fix 工具

**功能：** 修复图层的拓扑错误，输出修复后的新图层。

**LLM 函数定义：**

```json
{
    "type": "function",
    "function": {
        "name": "topology_fix",
        "description": "修复矢量图层的拓扑错误，输出修复后的新图层（原图层不变）。",
        "parameters": {
            "type": "object",
            "properties": {
                "layer_name": {
                    "type": "string",
                    "description": "要修复的图层名称"
                },
                "error_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要修复的错误类型列表（如 'dangle', 'self_intersection'）。不指定则修复所有可修复的错误"
                },
                "reference_layer": {
                    "type": "string",
                    "description": "跨图层规则的参考图层名称"
                },
                "dangle_threshold": {
                    "type": "number",
                    "description": "悬挂节点删除阈值，小于此值的悬挂节点被删除，默认 0.001"
                },
                "gap_tolerance": {
                    "type": "number",
                    "description": "缝隙填充容差，小于此值的缝隙被忽略，默认 0.0001"
                },
                "overlap_strategy": {
                    "type": "string",
                    "enum": ["trim", "merge"],
                    "description": "重叠处理策略：trim(裁剪) 或 merge(合并)，默认 trim"
                }
            },
            "required": ["layer_name"]
        }
    }
}
```

**输出：**
- 新图层：`<原图层名>_fixed`
- 保留原图层不变

**返回值：**
```python
{
    "success": True,
    "message": "拓扑修复完成，修复了 12 个错误",
    "results": [{
        "input": "roads",
        "output": "roads_fixed",
        "errors_fixed": 12,
        "fix_summary": {
            "dangle": 8,
            "self_intersection": 4
        },
        "errors_remaining": 3
    }]
}
```

---

## 4. 修复算法映射

| 错误类型 | 修复算法 | 参数 | 说明 |
|----------|----------|------|------|
| overlap | `native:difference` | overlap_strategy | 从较小要素中裁剪重叠部分 |
| gap | `native:buffer` + `native:dissolve` | gap_tolerance | 扩展相邻要素填充缝隙 |
| dangle | `native:extractbyexpression` | dangle_threshold | 删除短悬挂节点 |
| self_intersection | `native:fixgeometries` | - | 修复自相交几何 |
| duplicate_point | `native:removeduplicates` | - | 删除重复点 |
| invalid_geometry | `native:fixgeometries` | - | 修复无效几何 |
| pseudo_node | `native:extractbyexpression` | - | 删除伪节点 |

---

## 5. 实现计划

### 5.1 新增文件

- `tools/topology_check.py` - 拓扑检查工具实现
- `tools/topology_fix.py` - 拓扑修复工具实现

### 5.2 修改文件

- `tools/__init__.py` - 添加新工具导入
- `core/tool_registry.py` - 添加新工具定义

### 5.3 实现步骤

1. **创建拓扑规则映射表** (`tools/topology_rules.py`)
   - 定义规则名映射
   - 定义默认参数
   - 定义修复算法映射

2. **实现 topology_check 工具** (`tools/topology_check.py`)
   - 参数验证
   - 调用 QGIS `qgis:checkvalidity` 算法
   - 过滤和分类错误
   - 生成错误图层

3. **实现 topology_fix 工具** (`tools/topology_fix.py`)
   - 参数验证
   - 根据错误类型选择修复算法
   - 执行修复操作
   - 生成修复后图层

4. **注册工具** (`tools/__init__.py` + `core/tool_registry.py`)
   - 添加导入语句
   - 添加 LLM 函数定义

5. **测试**
   - 单元测试：测试各修复算法
   - 集成测试：测试完整工作流

---

## 6. 使用示例

### 6.1 基本检查

用户说："检查 roads 图层的拓扑错误"

AI 调用：
```json
{
    "tool": "topology_check",
    "params": {
        "layer_name": "roads",
        "rules": ["no_dangles", "no_self_intersections", "invalid_geometry"]
    }
}
```

输出：`roads_topology_errors` 图层

### 6.2 指定阈值

用户说："检查悬挂节点，阈值设为 0.5 米"

AI 调用：
```json
{
    "tool": "topology_check",
    "params": {
        "layer_name": "roads",
        "rules": ["no_dangles"],
        "dangle_threshold": 0.5
    }
}
```

### 6.3 修复错误

用户说："修复这些拓扑错误"

AI 调用：
```json
{
    "tool": "topology_fix",
    "params": {
        "layer_name": "roads",
        "error_types": ["dangle", "self_intersection"],
        "dangle_threshold": 0.5
    }
}
```

输出：`roads_fixed` 图层

### 6.4 跨图层检查

用户说："检查点图层是否都在面图层内"

AI 调用：
```json
{
    "tool": "topology_check",
    "params": {
        "layer_name": "points",
        "rules": ["point_in_polygon"],
        "reference_layer": "polygons"
    }
}
```

### 6.5 检查所有规则

用户说："全面检查 parcels 图层的拓扑"

AI 调用：
```json
{
    "tool": "topology_check",
    "params": {
        "layer_name": "parcels"
    }
}
```

---

## 7. 错误处理

### 7.1 参数验证

- 图层不存在 → 返回错误提示
- 规则不支持 → 返回错误提示并列出支持的规则
- 跨图层规则缺少参考图层 → 返回错误提示

### 7.2 算法执行失败

- QGIS Processing 算法失败 → 捕获异常，返回错误信息
- 输出图层为空 → 提示无错误或检查失败

### 7.3 修复失败

- 某些错误无法自动修复 → 跳过并报告剩余错误数
- 修复后图层无效 → 回滚操作，返回错误提示

---

## 8. 未来扩展

### 8.1 可能的增强

- **拓扑规则自定义**：允许用户定义自定义规则
- **批量检查**：同时检查多个图层
- **拓扑容差配置**：更精细的容差控制
- **修复策略选择**：提供多种修复策略供选择
- **拓扑报告导出**：导出详细的拓扑检查报告

### 8.2 性能优化

- **增量检查**：只检查修改过的要素
- **并行处理**：多图层并行检查
- **缓存机制**：缓存检查结果，避免重复检查

---

## 9. 验收标准

### 9.1 功能验收

- [ ] 支持所有定义的拓扑规则
- [ ] 检查工具输出正确的错误图层
- [ ] 修复工具输出正确的修复后图层
- [ ] 支持默认参数和高级参数两种使用方式
- [ ] 跨图层规则正确处理

### 9.2 质量验收

- [ ] 单元测试覆盖率 > 80%
- [ ] 无内存泄漏
- [ ] 错误处理完善，不导致 QGIS 崩溃

### 9.3 用户体验验收

- [ ] AI 能正确理解用户的拓扑相关需求
- [ ] 工具调用参数符合用户预期
- [ ] 输出信息清晰易懂

---

## 10. 附录

### 10.1 QGIS 拓扑相关算法

- `qgis:checkvalidity` - 检查几何有效性
- `native:fixgeometries` - 修复几何错误
- `native:removeduplicates` - 删除重复要素
- `native:buffer` - 缓冲区（可用于零缓冲区修复）
- `native:difference` - 差异分析（可用于去除重叠）
- `native:intersection` - 相交分析
- `native:dissolve` - 溶解

### 10.2 相关文档

- [QGIS Processing 框架文档](https://docs.qgis.org/3.28/en/docs/user_manual/processing/)
- [QGIS 拓扑检查器](https://docs.qgis.org/3.28/en/docs/user_manual/processing_algs/qgis/vectorgeometry.html#check-validity)
