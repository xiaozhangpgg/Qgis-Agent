# Fix: ToolCard JSON 序列化崩溃

## 问题描述

使用 `batch_reproject`（坐标转换）工具时，侧边栏工具卡片抛出异常，导致 UI 崩溃：

```
TypeError: Object of type method is not JSON serializable
```

崩溃位置：`ui/tool_card.py:91` — `json.dumps(self._params, ...)`

## 根因分析

问题涉及三个模块的交互：

| 文件 | 角色 |
|------|------|
| `core/agent_engine.py` | `_WorkerThread`（子线程）发射 `tool_started` 信号 |
| `core/tool_registry.py` | `execute()` 就地修改 `params` dict，注入 `_confirm_callback` 方法 |
| `ui/tool_card.py` | 主线程槽函数，接收 `params` 并调用 `json.dumps` 序列化展示 |

**时序问题**：

```
Worker Thread                          Main Thread
─────────────                          ───────────
1. tool_started.emit(tool_args) ──────→ (queued, waiting)
2. registry.execute(tool_args)
   └─ tool_args["_confirm_callback"]   ← dict 被修改!
      = <bound method>                ←
                                       3. _on_tool_started(tool_args)
                                          └─ json.dumps(tool_args) 💥
```

由于信号跨线程发送，Qt 使用 **队列连接**（queued connection）：信号先入队，主线程在后续事件循环中才处理。此时 `tool_args` 已被 `execute()` 注入了不可序列化的 `_confirm_callback` 方法对象。

## 修复方案

### 1. 根因修复：发射 dict 副本（`agent_engine.py`）

```python
# Before
self.tool_started.emit(tool_name, tool_args)

# After
self.tool_started.emit(tool_name, dict(tool_args))
```

发射浅拷贝，断开与后续 `execute()` 修改的引用关系。

### 2. 防御性修复：安全序列化（`tool_card.py`）

```python
# Before
params_text = json.dumps(self._params, ensure_ascii=False, indent=2)

# After
params_text = json.dumps(self._params, ensure_ascii=False, indent=2,
                         default=lambda o: f"<{type(o).__name__}>")
```

`default` 回调确保任何非序列化对象（方法、QgsMapLayer 等）以类型名占位显示，而非崩溃。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `core/agent_engine.py:160` | `tool_args` → `dict(tool_args)` |
| `ui/tool_card.py:91-92` | `json.dumps` 增加 `default` 回调 |

## 验证

1. 打开 QGIS，加载任意矢量图层
2. 触发 `batch_reproject` 工具（如"将图层转换为 EPSG:4490"）
3. 侧边栏应正常显示工具卡片，参数以 JSON 格式展示
4. 无 `TypeError` 异常
