# QgisAgent Code Wiki

> 版本: 1.0.0 | QGIS 最低版本: 3.28 | 目标 QGIS 版本: 3.44 | Python 环境: QGIS 内置 Python + PyQt5

---

## 目录

1. [项目概述](#1-项目概述)
2. [项目架构](#2-项目架构)
3. [目录结构](#3-目录结构)
4. [核心模块详解](#4-核心模块详解)
   - 4.1 [插件入口 (`__init__.py` / `plugin.py`)](#41-插件入口)
   - 4.2 [核心引擎层 (`core/`)](#42-核心引擎层-core)
   - 4.3 [工具层 (`tools/`)](#43-工具层-tools)
   - 4.4 [UI 层 (`ui/`)](#44-ui-层-ui)
5. [数据流与交互流程](#5-数据流与交互流程)
6. [依赖关系](#6-依赖关系)
7. [项目运行方式](#7-项目运行方式)
8. [测试](#8-测试)

---

## 1. 项目概述

QgisAgent 是一个运行在 QGIS 3.x 中的 AI 助手侧边栏插件。用户通过自然语言描述 GIS 操作需求，AI 自动拆解任务并调用 QGIS Processing 框架中的 GIS 工具完成空间数据处理。

**核心特性:**

- 自然语言驱动的 GIS 操作（基于 LLM Function Calling）
- 支持多种 LLM 提供商（DeepSeek / 通义千问 / 智谱 / 自定义 OpenAI 兼容 API）
- SSE 流式响应 + 实时工具调用卡片展示
- 双数据来源（QGIS 项目图层 + 插件文件导入）
- SQLite 持久化对话历史
- 11 种 GIS 工具（矢量/栅格）
- 文件覆盖确认机制

---

## 2. 项目架构

```
┌─────────────────────────────────────────────────────────┐
│                      QGIS 主程序                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │              QgisAgentPlugin (plugin.py)           │  │
│  │  classFactory → 插件加载 → 创建 Sidebar            │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                               │
│  ┌───────────────────────▼───────────────────────────┐  │
│  │                 UI 层 (ui/)                        │  │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │  │
│  │  │ Sidebar  │ │ Settings │ │ MessageWidget     │  │  │
│  │  │ Widget   │ │ Dialog   │ │ + ToolCardWidget  │  │  │
│  │  └────┬─────┘ └──────────┘ └───────────────────┘  │  │
│  └───────┼───────────────────────────────────────────┘  │
│          │                                              │
│  ┌───────▼───────────────────────────────────────────┐  │
│  │              核心引擎层 (core/)                     │  │
│  │  ┌──────────────┐  ┌────────────────┐             │  │
│  │  │ AgentEngine  │  │  LLMClient     │             │  │
│  │  │ (Agent Loop) │──│  (SSE Stream)  │             │  │
│  │  └──────┬───────┘  └────────────────┘             │  │
│  │         │                                          │  │
│  │  ┌──────▼───────┐  ┌────────────────┐             │  │
│  │  │ ToolRegistry │  │ ContextManager │             │  │
│  │  │ (工具注册/调度)│  │ (项目上下文收集)│             │  │
│  │  └──────┬───────┘  └────────────────┘             │  │
│  │         │           ┌────────────────┐             │  │
│  │         │           │FileSourceMgr   │             │  │
│  │         │           │(双数据源管理)   │             │  │
│  │         │           └────────────────┘             │  │
│  │  ┌──────▼───────┐  ┌────────────────┐             │  │
│  │  │Conversation  │  │                │             │  │
│  │  │Manager       │  │                │             │  │
│  │  │(SQLite持久化) │  │                │             │  │
│  │  └──────────────┘  └────────────────┘             │  │
│  └───────────────────────────────────────────────────┘  │
│          │                                              │
│  ┌───────▼───────────────────────────────────────────┐  │
│  │                工具层 (tools/)                      │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐  │  │
│  │  │batch_  │ │batch_  │ │buffer  │ │overlay     │  │  │
│  │  │reproject│ │clip   │ │        │ │            │  │  │
│  │  └────────┘ └────────┘ └────────┘ └────────────┘  │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐  │  │
│  │  │attrib_ │ │spatial │ │raster_ │ │format_     │  │  │
│  │  │query   │ │query   │ │calc    │ │convert     │  │  │
│  │  └────────┘ └────────┘ └────────┘ └────────────┘  │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐                  │  │
│  │  │batch_  │ │statist │ │field_  │                  │  │
│  │  │export  │ │ics     │ │calc    │                  │  │
│  │  └────────┘ └────────┘ └────────┘                  │  │
│  └───────────────────────────────────────────────────┘  │
│                          │                               │
│               QGIS Processing 框架                       │
│          (native:buffer, native:clip, ...)               │
└─────────────────────────────────────────────────────────┘
```

**架构分层:**

| 层级 | 目录 | 职责 |
|------|------|------|
| 插件入口 | 根目录 | QGIS 插件生命周期管理、日志配置 |
| UI 层 | `ui/` | 用户交互界面（侧边栏、设置、消息、工具卡片） |
| 核心引擎层 | `core/` | Agent 循环、LLM 通信、工具注册调度、上下文管理、对话持久化、数据源管理 |
| 工具层 | `tools/` | 11 个 GIS 工具的具体实现，调用 QGIS Processing 算法 |

---

## 3. 目录结构

```
QgisAgent/
├── __init__.py              # 插件入口 + 日志配置
├── plugin.py                # QgisAgentPlugin 类（QGIS 插件主类）
├── metadata.txt             # QGIS 插件元数据
├── icon.png                 # 插件图标
├── resources.qrc            # Qt 资源文件
├── resources_rc.py          # Qt 资源编译产物
├── .gitignore
├── CLAUDE.md                # 开发指引
├── README.md
│
├── core/                    # 核心引擎层
│   ├── __init__.py
│   ├── agent_engine.py      # Agent 引擎（LLM + 工具循环）
│   ├── llm_client.py        # LLM 客户端（SSE 流式 + Function Calling）
│   ├── tool_registry.py     # 工具注册表 + JSON Schema 定义
│   ├── context_manager.py   # QGIS 项目上下文收集
│   ├── conversation_manager.py  # 对话历史 SQLite 持久化
│   └── file_source_manager.py   # 双数据源管理（项目图层 + 文件导入）
│
├── tools/                   # GIS 工具实现
│   ├── __init__.py          # 工具导出
│   ├── _utils.py            # 公共工具函数
│   ├── batch_reproject.py   # 批量坐标转换
│   ├── batch_clip.py        # 批量裁剪
│   ├── buffer.py            # 缓冲区分析
│   ├── overlay.py           # 叠加分析
│   ├── attribute_query.py   # 属性查询
│   ├── spatial_query.py     # 空间查询
│   ├── raster_calculator.py # 栅格计算器
│   ├── format_convert.py    # 格式转换
│   ├── batch_export.py      # 批量导出
│   ├── statistics.py        # 统计汇总
│   ├── field_calculator.py  # 字段计算器
│
├── ui/                      # UI 组件
│   ├── __init__.py
│   ├── sidebar.py           # 侧边栏主界面
│   ├── message_widget.py    # 消息气泡组件
│   ├── settings_dialog.py   # 设置对话框
│   └── tool_card.py         # 工具调用卡片组件
│
└── docs/                    # 文档
    ├── Development_Plan.md
    ├── PRD_Acceptance_Criteria.md
    └── fix-tool-card-json-serialize-error.md
```

---

## 4. 核心模块详解

### 4.1 插件入口

#### `__init__.py`

| 项目 | 说明 |
|------|------|
| 日志配置 | 创建 `QgsMessageLogHandler`，将 Python `logging` 桥接到 QGIS 消息日志面板 |
| 入口函数 | `classFactory(iface)` — QGIS 插件加载入口，返回 `QgisAgentPlugin` 实例 |

**关键类:**

- **`QgsMessageLogHandler(logging.Handler)`** — 自定义日志处理器，将 Python logging 输出重定向到 QGIS Message Log，自动映射日志级别（DEBUG/INFO → Qgis.Info, WARNING → Qgis.Warning, ERROR/CRITICAL → Qgis.Critical）

#### `plugin.py`

| 项目 | 说明 |
|------|------|
| 类 | `QgisAgentPlugin` |
| 职责 | QGIS 插件生命周期管理 |

**关键方法:**

| 方法 | 说明 |
|------|------|
| `__init__(iface)` | 保存 `iface` 引用，初始化属性 |
| `initGui()` | 插件加载入口：创建 LLMClient、从 QgsSettings 恢复配置、添加工具栏按钮、创建侧边栏 |
| `unload()` | 插件卸载：移除工具栏图标、菜单项、销毁侧边栏 |
| `_create_sidebar()` | 创建 `SidebarWidget` 并添加到 QGIS 主窗口右侧 Dock 区域 |
| `_toggle_sidebar(checked)` | 切换侧边栏显示/隐藏 |

---

### 4.2 核心引擎层 (`core/`)

#### `core/agent_engine.py` — Agent 引擎

整个 Agent 的核心，实现 LLM 与工具调用的循环（ReAct 模式）。

**常量:**

| 常量 | 值 | 说明 |
|------|----|------|
| `MAX_AGENT_LOOPS` | 10 | Agent 循环最大次数（防止无限循环） |
| `MAX_HISTORY_MESSAGES` | 20 | 发送给 LLM 的最大历史消息数 |
| `SYSTEM_PROMPT_TEMPLATE` | — | 系统提示词模板，包含工具定义、项目上下文、数据来源说明、工作规则 |

**关键类:**

- **`_WorkerThread(QThread)`** — 后台工作线程，执行 LLM + 工具循环

| 信号 | 参数 | 说明 |
|------|------|------|
| `text_chunk` | `(str)` | LLM 流式文本片段 |
| `text_done` | — | LLM 文本输出完成 |
| `tool_started` | `(str, dict)` | 工具开始执行（名称, 参数） |
| `tool_finished` | `(str, bool, str, float)` | 工具执行完成（名称, 成功, 结果消息, 耗时） |
| `error` | `(str)` | 错误消息 |
| `finished` | — | 工作线程结束 |
| `confirm_overwrite` | `(str)` | 请求用户确认文件覆盖 |
| `confirm_response` | `(bool, bool)` | 用户确认响应（确认, 应用到全部） |

| 方法 | 说明 |
|------|------|
| `run()` | 线程入口，调用 `_run_loop()` |
| `_run_loop()` | 核心 Agent 循环：构建 system prompt → 调用 LLM → 解析响应 → 若有 tool_calls 则执行工具并继续循环 → 若 stop 则结束 |
| `_build_system_prompt()` | 组装系统提示词（工具定义 + 项目上下文 + 数据来源） |
| `_build_messages(system_prompt)` | 构建 LLM 消息列表（system + 最近 N 条历史） |
| `_ask_user_confirm(message)` | 通过 QEventLoop 阻塞等待用户确认（线程安全） |
| `abort()` | 中断当前执行 |

- **`AgentEngine(QObject)`** — Agent 引擎主类，UI 与 Worker 之间的桥梁

| 方法 | 说明 |
|------|------|
| `__init__(llm_client, iface, file_source_mgr)` | 初始化引擎，注册所有工具 |
| `_register_tools()` | 注册 11 个工具到 ToolRegistry |
| `run(user_text, attached_files)` | 启动 Agent：处理附件 → 解析数据来源 → 追加用户消息 → 启动 WorkerThread |
| `abort()` | 中断当前执行 |
| `clear_history()` | 清空消息历史 |

**Agent 循环流程:**

```
用户输入 → run() → WorkerThread._run_loop()
  │
  ├─ 1. 构建 system prompt（工具定义 + 项目上下文 + 数据来源）
  ├─ 2. 调用 LLM (SSE 流式)
  │     ├─ finish_reason="stop" → 输出文本，结束
  │     └─ finish_reason="tool_calls" → 执行工具
  ├─ 3. 逐个执行 tool_calls
  │     ├─ 发射 tool_started 信号
  │     ├─ ToolRegistry.execute() 调用工具函数
  │     ├─ 发射 tool_finished 信号
  │     └─ 将工具结果追加到消息列表
  ├─ 4. 回到步骤 1（最多 MAX_AGENT_LOOPS 次）
  └─ 结束
```

---

#### `core/llm_client.py` — LLM 客户端

实现 OpenAI 兼容 API 的 SSE 流式通信和 Function Calling。

**数据类:**

- **`ProviderConfig`** — LLM 提供商配置（name, base_url, models, default_model）
- **`LLMResponse`** — LLM 响应数据（content, reasoning_content, tool_calls, finish_reason, error）

**预定义提供商:**

| Key | 名称 | Base URL | 默认模型 |
|-----|------|----------|----------|
| `deepseek` | DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat |
| `tongyi` | 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-plus |
| `zhipu` | 智谱 | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash |
| `custom` | 自定义 | （用户填写） | （用户填写） |

**关键类:**

- **`LLMClient`** — OpenAI 兼容 LLM 客户端

| 方法 | 说明 |
|------|------|
| `configure(provider_key, api_key, model, base_url, timeout)` | 配置提供商和认证信息 |
| `is_configured` (property) | 是否已完成配置（api_key + base_url + model 非空） |
| `test_connection()` → `(bool, str)` | 测试 API 连接（发送简短请求验证 Key 有效性） |
| `fetch_models()` → `(bool, str/list)` | 从 API `/v1/models` 端点获取可用模型列表 |
| `chat_stream(messages, tools)` → `Generator[LLMResponse]` | SSE 流式聊天（支持 Function Calling） |
| `chat(messages, tools)` → `LLMResponse` | 同步聊天（聚合所有流式片段） |
| `_stream_with_tools(messages, tools)` | 带 Function Calling 的 SSE 流式请求，增量拼接 tool_calls |
| `_stream_plain(messages)` | 纯文本 SSE 流式请求 |
| `abort()` | 中断当前请求 |
| `_parse_error(resp)` | 解析 HTTP 错误响应为中文提示 |

---

#### `core/tool_registry.py` — 工具注册表

管理工具名称到函数的映射，以及 OpenAI Function Calling 所需的 JSON Schema 定义。

**关键数据:**

- **`TOOL_DEFINITIONS`** — 11 个工具的 JSON Schema 定义列表，用于 LLM Function Calling 的 `tools` 参数
- **`ConfirmResult`** — 用户确认结果数据类（confirmed, apply_to_all）

**关键类:**

- **`ToolRegistry`** — 工具注册表

| 方法 | 说明 |
|------|------|
| `register(name, func)` | 注册工具（名称 → 函数映射） |
| `get_definitions()` → `List[Dict]` | 获取所有工具的 JSON Schema 定义 |
| `execute(name, params)` → `Dict` | 执行工具：查找函数 → 注入 `_confirm_callback`/`_ask_dir_callback` → 调用 → 返回结果 |
| `set_confirm_callback(callback)` | 设置文件覆盖确认回调 |
| `set_ask_dir_callback(callback)` | 设置目录选择回调 |
| `has_tool(name)` → `bool` | 检查工具是否已注册 |

**已注册的 11 个工具:**

| 工具名 | 函数 | 说明 |
|--------|------|------|
| `batch_reproject` | `run_batch_reproject` | 批量坐标转换 |
| `batch_clip` | `run_batch_clip` | 批量裁剪 |
| `buffer` | `run_buffer` | 缓冲区分析 |
| `overlay` | `run_overlay` | 叠加分析 |
| `attribute_query` | `run_attribute_query` | 属性查询 |
| `spatial_query` | `run_spatial_query` | 空间查询 |
| `raster_calculator` | `run_raster_calculator` | 栅格计算器 |
| `format_convert` | `run_format_convert` | 格式转换 |
| `batch_export` | `run_batch_export` | 批量导出 |
| `statistics` | `run_statistics` | 统计汇总 |
| `field_calculator` | `run_field_calculator` | 字段计算器 |

---

#### `core/context_manager.py` — 项目上下文管理

收集当前 QGIS 项目状态，注入到 LLM 系统提示词中，使 LLM 了解可用图层信息。

**关键类:**

- **`ContextManager`**

| 方法 | 说明 |
|------|------|
| `__init__(iface)` | 保存 iface 引用 |
| `collect_context(source_filter)` → `Dict` | 收集项目上下文：图层列表、项目 CRS、选中图层 |
| `collect_context_json(source_filter)` → `str` | 收集上下文并返回 JSON 字符串 |
| `get_layer_names(source_filter)` → `List[str]` | 获取所有图层名称 |
| `get_layer_by_name(name)` → `QgsMapLayer/None` | 按名称查找图层 |
| `validate_layer_exists(name)` → `bool` | 验证图层是否存在 |
| `validate_crs(crs_str)` → `bool` | 验证 CRS 字符串有效性 |

**上下文数据结构:**

```json
{
  "layers": [
    {
      "name": "图层名",
      "type": "vector|raster|unknown",
      "crs": "EPSG:4326 (WGS 84)",
      "geometry_type": "Point|LineString|Polygon",
      "feature_count": 100,
      "fields": ["field1", "field2"],
      "source": "project|plugin"
    }
  ],
  "project_crs": "EPSG:4326",
  "selected_layers": ["图层A"],
  "layer_count": 3
}
```

---

#### `core/conversation_manager.py` — 对话持久化

基于 SQLite 的对话历史存储，支持对话的创建、加载、搜索、删除。

**数据类:**

- **`ConversationMessage`** — 消息（role, content, timestamp, metadata）
- **`Conversation`** — 对话（id, title, created_at, updated_at, messages, metadata）
- **`ConversationSummary`** — 对话摘要（id, title, updated_at, message_count, preview）

**数据库位置:** `{QgsApplication.qgisSettingsDirPath()}/QgisAgent/conversations.db`

**数据库表:**

| 表名 | 字段 | 说明 |
|------|------|------|
| `conversations` | id, title, created_at, updated_at, metadata | 对话元数据 |
| `messages` | id, conversation_id, role, content, timestamp, metadata | 消息记录（外键关联 conversations） |

**关键类:**

- **`ConversationManager`**

| 方法 | 说明 |
|------|------|
| `create_new()` → `str` | 创建新对话，返回对话 ID |
| `get_current_id()` → `str/None` | 获取当前对话 ID |
| `save_message(conv_id, role, content, metadata)` | 保存消息 |
| `update_title(conv_id, title)` | 更新对话标题 |
| `list_conversations()` → `List[ConversationSummary]` | 列出所有对话（按更新时间降序） |
| `load_conversation(conv_id)` → `Conversation/None` | 加载完整对话 |
| `delete_conversation(conv_id)` | 删除对话及其所有消息 |
| `search_conversations(query)` → `List[ConversationSummary]` | 搜索对话（标题 + 内容模糊匹配） |
| `update_metadata(conv_id, metadata)` | 更新对话元数据（合并） |
| `get_metadata(conv_id)` → `Dict` | 获取对话元数据 |

---

#### `core/file_source_manager.py` — 双数据源管理

管理两种数据来源：QGIS 项目中已有的图层（project）和用户通过插件导入的文件（plugin）。

**枚举类:**

- **`LayerSource`** — PROJECT / PLUGIN
- **`SourceDecision`** — NO_LAYERS / ASK_USER / USE_PROJECT / USE_PLUGIN

**数据类:**

- **`ManagedFile`** — 管理的导入文件（file_path, display_name, layer_name, source, is_loaded, load_error, layer_id）

**支持的文件格式:**

| 类型 | 扩展名 |
|------|--------|
| 矢量 | `.shp`, `.geojson`, `.gpkg`, `.kml`, `.tab` |
| 栅格 | `.tif`, `.tiff`, `.img`, `.asc` |

**关键类:**

- **`FileSourceManager(QObject)`**

| 方法 | 说明 |
|------|------|
| `add_file(file_path)` → `ManagedFile/None` | 添加文件到管理列表 |
| `remove_file(display_name)` | 移除文件并卸载图层 |
| `clear_all()` | 清除所有导入文件 |
| `load_all_to_qgis()` → `List[str]` | 将所有文件加载为 QGIS 图层 |
| `resolve_source()` → `SourceDecision` | 解析应使用哪种数据源 |
| `get_source_description()` → `str` | 获取数据来源描述文本 |
| `set_source_override(source)` | 设置数据来源覆盖 |
| `has_files()` / `has_project_layers()` | 检查数据源是否存在 |

**数据来源决策逻辑:**

```
resolve_source():
  无项目图层 & 无插件文件 → NO_LAYERS
  有覆盖设置 → 使用覆盖
  仅有项目图层 → USE_PROJECT
  仅有插件文件 → USE_PLUGIN
  两者都有 → ASK_USER（弹窗让用户选择）
```

导入的文件图层以 `[plugin] ` 前缀命名，并设置自定义属性 `qgis_agent_source = "plugin"` 以区分来源。

---

### 4.3 工具层 (`tools/`)

#### `tools/_utils.py` — 公共工具函数

| 函数 | 说明 |
|------|------|
| `find_layer(name)` → `QgsMapLayer/None` | 按名称精确查找图层 |
| `find_layer_with_warnings(name)` → `(layer, warnings)` | 按名称查找图层，返回同名图层警告 |
| `find_layer_case_insensitive(name)` → `QgsMapLayer/None` | 忽略大小写查找图层 |
| `resolve_input(layer)` | 解析图层输入源（文件路径或图层对象） |
| `resolve_output_name(project, base_name)` | 生成不重复的输出图层名 |

**常量映射:**

| 常量 | 说明 |
|------|------|
| `FORMAT_EXTENSIONS` | 格式 → 扩展名映射（geojson/gpkg/kml/csv/shp/gml） |
| `DRIVER_MAP` | 格式 → OGR 驱动名映射 |

---

#### 各工具函数详解

所有工具函数遵循统一接口约定：

- **输入:** 具名参数（与 `TOOL_DEFINITIONS` 中的 JSON Schema 对应），可选 `_confirm_callback`、`_ask_dir_callback`
- **输出:** `Dict[str, Any]`，至少包含 `success` (bool) 和 `message`/`error` (str)

##### `run_batch_reproject(layer_names, target_crs, output_format, _confirm_callback, _ask_dir_callback)`

批量将多个矢量图层转换到目标 CRS 并导出为文件。

- 调用 `native:reprojectlayer` Processing 算法
- 通过 `_ask_dir_callback` 弹出目录选择对话框，让用户指定保存位置
- 支持 `output_format` 参数选择导出格式（shp/gpkg/geojson/kml/csv）
- 支持 CRS 不匹配检测（输出 CRS 与目标 CRS 比对）
- 输出文件覆盖确认
- 返回每个图层的转换前后要素数、CRS 信息、输出文件路径

##### `run_batch_clip(layer_names, clip_layer, _confirm_callback)`

使用裁剪边界图层批量裁剪多个图层。

- 调用 `native:clip` Processing 算法
- 验证裁剪边界为面图层、CRS 一致性
- 不允许裁剪自身

##### `run_buffer(layer_name, distance, segments, dissolve, _confirm_callback)`

对图层要素创建缓冲区。

- 调用 `native:buffer` Processing 算法
- 地理坐标系自动重投影：先重投影到合适的投影坐标系（优先项目 CRS，否则 UTM），执行缓冲区，再重投影回源坐标系
- `_find_suitable_projected_crs()` — 查找合适的投影 CRS
- `_compute_utm_crs(lon, lat)` — 根据经纬度计算 UTM EPSG 代码

##### `run_overlay(layer_a, layer_b, operation, _confirm_callback)`

对两个矢量图层执行叠加分析。

- 支持 `intersection`（相交）、`union`（联合）、`difference`（差异）
- 分别调用 `native:intersection`、`native:union`、`native:difference`
- 验证 CRS 一致性、不允许非 union 操作对同一图层

##### `run_attribute_query(layer_name, expression, _confirm_callback)`

根据 QGIS 表达式从图层中提取满足条件的要素。

- 调用 `native:extractbyexpression` Processing 算法
- 先用 `QgsExpression` 验证表达式语法

##### `run_spatial_query(layer_name, reference_layer, predicate)`

根据空间关系从图层中提取要素。

- 调用 `native:extractbylocation` Processing 算法
- 支持 8 种空间谓词：intersects, contains, disjoint, equals, touches, overlaps, within, crosses

##### `run_raster_calculator(expression, input_rasters, output_name, cellsize, _confirm_callback)`

使用表达式对栅格图层进行计算。

- 调用 `native:rastercalc` Processing 算法
- 输出到临时 TIF 文件后加载为项目图层
- `_extract_referenced_layers()` — 从表达式中提取引用的图层名

##### `run_format_convert(layer_name, output_format, output_dir, _confirm_callback)`

将矢量图层转换为其他格式。

- 调用 `native:savefeatures` Processing 算法
- 支持 geojson/gpkg/kml/csv/shp/gml
- 指定输出目录则保存文件，否则添加为临时图层

##### `run_batch_export(layer_names, output_format, output_dir, _confirm_callback)`

批量将多个图层导出为指定格式的文件。

- 调用 `native:savefeatures` Processing 算法
- 必须指定输出目录
- 支持部分成功（partial_success）

##### `run_statistics(layer_name, value_field, category_field, _confirm_callback)`

对图层字段进行统计汇总。

- 有分类字段时：调用 `qgis:statisticsbycategories`，输出分组统计图层
- 无分类字段时：调用 `qgis:basicstatisticsforfields`，返回 count/unique/min/max/range/sum/mean/median/stddev

##### `run_field_calculator(layer_name, field_name, formula, field_type, field_length, field_precision, output_name)`

使用 QGIS 表达式进行字段计算。

- 调用 `native:fieldcalculator` Processing 算法
- 支持 float/integer/string/date/time/datetime/boolean 字段类型
- 自动处理字段长度和精度默认值

---

### 4.4 UI 层 (`ui/`)

#### `ui/sidebar.py` — 侧边栏主界面

QGIS Agent 的主交互界面，基于 `QDockWidget`。

**关键类:**

- **`MessageInput(QTextEdit)`** — 多行输入框，Enter 发送，Shift+Enter 换行，自动调整高度

- **`SidebarWidget(QDockWidget)`** — 侧边栏主组件

| 组件 | 说明 |
|------|------|
| 顶部栏 | 标题 + 新对话/历史/设置按钮 |
| 聊天视图 | 消息滚动区 + 文件附件区 + 输入区 |
| 历史视图 | 搜索框 + 对话列表（支持点击加载、右键删除） |

| 核心方法 | 说明 |
|----------|------|
| `_on_send()` | 发送消息：创建对话 → 保存消息 → 处理附件 → 启动引擎 |
| `_on_ai_text_chunk(chunk)` | 接收 LLM 流式文本片段 |
| `_on_ai_text_done()` | LLM 文本完成，保存到对话历史 |
| `_on_tool_started(tool_name, params)` | 创建工具卡片 |
| `_on_tool_finished(tool_name, success, result, elapsed)` | 更新工具卡片结果 |
| `_on_add_file()` | 文件选择对话框，添加矢量/栅格文件 |
| `_on_new_chat()` | 新建对话（确认清理临时图层） |
| `_load_conversation(conv_id)` | 加载历史对话（恢复消息和附件） |

---

#### `ui/message_widget.py` — 消息组件

| 类 | 说明 |
|----|------|
| `UserMessageWidget(QFrame)` | 用户消息气泡，绿色强调条，纯文本显示 |
| `AiMessageWidget(QFrame)` | AI 消息气泡，蓝色强调条，支持流式追加、光标闪烁、Markdown 格式化 |

**Markdown 格式化支持:** 代码块、行内代码、粗体、标题（H1-H3）、列表、换行

---

#### `ui/settings_dialog.py` — 设置对话框

| 类 | 说明 |
|----|------|
| `SettingsDialog(QDialog)` | API 配置对话框 |

**配置项:** Provider、Model（可编辑下拉 + 获取模型列表）、Base URL、API Key（密码模式 + 显示/隐藏切换）

**持久化:** 通过 `QgsSettings` 保存到 `QgisAgent/provider`、`QgisAgent/api_key`、`QgisAgent/model`、`QgisAgent/base_url`

**功能:** 测试连接、获取模型列表、保存配置

---

#### `ui/tool_card.py` — 工具调用卡片

| 类 | 说明 |
|----|------|
| `ToolCardWidget(QFrame)` | 可折叠的工具调用卡片 |

**状态:** running（蓝色）→ success（绿色）/ error（红色）

**显示内容:** 工具名、参数 JSON、执行结果、耗时

---

## 5. 数据流与交互流程

### 5.1 完整的用户交互流程

```
1. 用户在 QGIS 中点击工具栏按钮 → 插件加载 → 侧边栏显示
2. 首次使用：点击"设置" → 配置 Provider/API Key/Model → 保存
3. 用户输入自然语言消息（可选附加文件）→ 点击发送
4. SidebarWidget._on_send():
   a. 确保对话存在（ConversationManager.create_new）
   b. 保存用户消息到 SQLite
   c. 首条消息自动生成对话标题
   d. 如有附件，FileSourceManager 加载文件到 QGIS
   e. 解析数据来源（项目图层 vs 插件文件）
   f. AgentEngine.run() 启动
5. AgentEngine 启动 WorkerThread:
   a. 构建 system prompt（工具定义 + 项目上下文 + 数据来源）
   b. 调用 LLM SSE 流式接口
   c. 流式文本 → text_chunk 信号 → AiMessageWidget 追加显示
   d. 若 LLM 返回 tool_calls:
      - 逐个执行工具 → ToolRegistry.execute()
      - 工具函数调用 QGIS Processing 算法
      - 结果追加到消息列表
      - 继续循环
   e. 若 LLM 返回 stop → 保存 AI 回复 → 结束
6. 结果展示：AI 文本 + 工具卡片（可折叠查看参数和结果）
```

### 5.2 文件覆盖确认流程

```
工具函数检测到文件已存在
  → 调用 _confirm_callback(message)
  → WorkerThread._ask_user_confirm()
  → 发射 confirm_overwrite 信号到主线程
  → 主线程弹出 QMessageBox
  → 用户选择 → 发射 confirm_response 信号回 WorkerThread
  → QEventLoop 退出 → 返回 ConfirmResult
```

### 5.3 目录选择流程

```
工具函数需要用户指定输出目录
  → 调用 _ask_dir_callback(message)
  → WorkerThread._ask_user_directory()
  → 发射 ask_directory 信号到主线程
  → 主线程弹出 QFileDialog.getExistingDirectory()
  → 用户选择目录 → 发射 directory_response 信号回 WorkerThread
  → QEventLoop 退出 → 返回目录路径（空字符串表示取消）
```

### 5.4 双数据来源决策流程

```
用户发送消息时:
  ├─ 有附件 → FileSourceManager.load_all_to_qgis() 加载文件
  ├─ resolve_source() 判断:
  │   ├─ 仅项目图层 → USE_PROJECT
  │   ├─ 仅插件文件 → USE_PLUGIN
  │   ├─ 两者都有 → ASK_USER → 弹窗让用户选择
  │   └─ 都没有 → NO_LAYERS
  └─ 决策结果影响 ContextManager 的 source_filter
      → system prompt 中只包含对应来源的图层信息
```

---

## 6. 依赖关系

### 6.1 外部依赖

| 依赖 | 用途 | 来源 |
|------|------|------|
| `qgis.core` | QGIS 核心API（QgsProject, QgsVectorLayer, QgsRasterLayer, QgsCoordinateReferenceSystem 等） | QGIS 内置 |
| `qgis.PyQt.QtWidgets` | PyQt5 UI 组件 | QGIS 内置 |
| `qgis.PyQt.QtCore` | PyQt5 核心类（QObject, QThread, pyqtSignal 等） | QGIS 内置 |
| `qgis.PyQt.QtGui` | PyQt5 GUI 类（QIcon, QPalette 等） | QGIS 内置 |
| `processing` | QGIS Processing 框架（算法调用） | QGIS 内置 |
| `requests` | HTTP 请求（LLM API 调用） | Python 标准库/第三方 |
| `sqlite3` | SQLite 数据库（对话持久化） | Python 标准库 |
| `pytest` | 测试框架 | 开发依赖 |

### 6.2 模块间依赖关系

```
plugin.py
  ├── core.llm_client.LLMClient
  ├── core.agent_engine.AgentEngine
  ├── core.conversation_manager.ConversationManager
  ├── core.file_source_manager.FileSourceManager
  └── ui.sidebar.SidebarWidget

ui/sidebar.py
  ├── ui.message_widget (UserMessageWidget, AiMessageWidget)
  ├── ui.tool_card.ToolCardWidget
  ├── ui.settings_dialog.SettingsDialog
  ├── core.llm_client.LLMClient
  ├── core.agent_engine.AgentEngine
  ├── core.conversation_manager.ConversationManager
  └── core.file_source_manager.FileSourceManager

core/agent_engine.py
  ├── core.llm_client (LLMClient, LLMResponse)
  ├── core.tool_registry (ToolRegistry, ConfirmResult)
  ├── core.context_manager.ContextManager
  ├── core.file_source_manager (FileSourceManager, SourceDecision)
  └── tools.* (所有 11 个工具函数)

core/tool_registry.py
  └── (独立，无内部依赖)

core/context_manager.py
  └── qgis.core (QgsProject, QgsVectorLayer, QgsRasterLayer)

core/conversation_manager.py
  └── qgis.core.QgsApplication

core/file_source_manager.py
  └── qgis.core (QgsProject, QgsVectorLayer, QgsRasterLayer)

tools/* → tools/_utils.py (find_layer, resolve_input, FORMAT_EXTENSIONS, DRIVER_MAP)
```

---

## 7. 项目运行方式

### 7.1 安装

1. 将整个 `QgisAgent` 目录复制到 QGIS 插件目录：
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\QgisAgent\`
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/QgisAgent/`
   - **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/QgisAgent/`

2. 在 QGIS 中启用插件：菜单 → 插件 → 管理和安装插件 → 已安装 → 勾选 "QGIS Agent"

### 7.2 配置

1. 点击工具栏 QGIS Agent 图标打开侧边栏
2. 点击"设置"按钮
3. 选择 Provider（DeepSeek / 通义千问 / 智谱 / 自定义）
4. 输入 API Key
5. 选择或输入 Model 名称
6. 可选：测试连接
7. 保存

### 7.3 使用

1. 在 QGIS 中加载图层
2. 在侧边栏输入自然语言描述 GIS 操作
3. 可选：点击 📎 按钮添加本地文件
4. AI 自动拆解任务并调用工具执行
5. 查看工具执行卡片了解详情

### 7.4 开发调试

- QGIS 版本目标: 3.44
- Python 环境: QGIS 内置 Python + PyQt5
- 测试: `pytest tests/`
- API 文档: https://qgis.org/pyqgis/3.44/
- 日志输出: QGIS 消息日志面板 → "QgisAgent" 标签

---

## 8. 测试

当前暂无测试覆盖。
