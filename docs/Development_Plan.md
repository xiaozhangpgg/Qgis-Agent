# QGIS Agent 插件开发计划

**产品名称：** QGIS Agent
**版本：** 1.0.0
**目标平台：** QGIS 4.0.0-1 (Windows / macOS / Linux)
**文档版本：** 1.0
**日期：** 2026-05-08

---

## 1. 项目概述

### 1.1 背景

GIS 用户在日常工作中面临大量重复性操作（批量转坐标系、批量裁剪等），且 QGIS 的 Processing 工具箱对新手不够友好。本插件在 QGIS 4.0 右侧以侧边栏形式提供一个 AI 对话助手，用户通过自然语言描述需求，AI 自动拆解为子任务并调用相应的 GIS 工具完成操作。

### 1.2 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| UI 框架 | `qgis.PyQt` (Qt6/PyQt6) | QGIS 4.0 官方兼容层，跨平台 |
| LLM 协议 | OpenAI 兼容协议 | 天然支持 DeepSeek/通义千问/智谱等国产模型 |
| HTTP 客户端 | `requests` + SSE | QGIS 内置，无需额外依赖 |
| 数据存储 | SQLite (Python 内置 `sqlite3`) | 对话历史持久化，单文件，零依赖 |
| 异步模型 | `QThread` + Worker / `QgsTask` | API 调用用 QThread，GIS 工具用 QgsTask |

---

## 2. 项目目录结构

```
QgisAgent/
├── __init__.py                 # 插件入口 classFactory(iface)
├── plugin.py                   # 主插件类，管理生命周期
├── metadata.txt                # QGIS 插件元数据
├── icon.png                    # 插件图标
├── resources.qrc               # Qt 资源文件
├── resources_rc.py             # 编译后的资源文件
│
├── ui/                         # UI 层
│   ├── __init__.py
│   ├── sidebar.py              # 侧边栏 QDockWidget + 聊天 UI
│   ├── message_widget.py       # 单条消息气泡组件（用户/AI）
│   ├── tool_card.py            # 工具调用卡片组件（可折叠，状态指示）
│   └── settings_dialog.py      # 设置对话框（API Key、模型选择）
│
├── core/                       # 核心逻辑层
│   ├── __init__.py
│   ├── agent_engine.py         # Agent 引擎：任务拆解 + 工具调度
│   ├── llm_client.py           # LLM API 客户端（OpenAI 兼容协议）
│   ├── tool_registry.py        # GIS 工具注册表 + 函数定义
│   ├── context_manager.py      # 项目上下文收集（图层列表、CRS 等）
│   ├── file_source_manager.py  # 文件源管理（插件添加文件 vs 项目图层）
│   └── conversation_manager.py # 对话历史管理（创建/保存/切换/删除）
│
├── tools/                      # GIS 工具实现
│   ├── __init__.py
│   ├── batch_reproject.py      # 批量坐标转换 (P0)
│   ├── batch_clip.py           # 批量裁剪 (P0)
│   ├── buffer.py               # 缓冲区分析 (P0)
│   ├── overlay.py              # 叠加分析 (P1)
│   ├── attribute_query.py      # 属性查询 (P1)
│   ├── spatial_query.py        # 空间查询 (P1)
│   ├── raster_calculator.py    # 栅格计算 (P1)
│   ├── format_convert.py       # 格式转换 (P1)
│   ├── batch_export.py         # 批量导出 (P1)
│   └── statistics.py           # 统计汇总 (P1)
│
├── i18n/                       # 翻译文件 (P1)
│   ├── zh_CN.ts
│   └── en_US.ts
└── tests/                      # 测试
    ├── test_llm_client.py
    ├── test_tools.py
    └── test_agent_engine.py
```

**包职责划分：**
- **根目录**：QGIS 插件加载机制要求 `__init__.py`、`plugin.py`、`metadata.txt` 必须在根目录
- **ui/**：所有 PyQt 界面组件，不包含业务逻辑
- **core/**：业务逻辑层，不依赖 PyQt 界面组件（除 file_source_manager 使用 QObject 信号）
- **tools/**：纯 GIS 工具实现，依赖 QGIS Processing API，不依赖 UI 或 core

---

## 3. 核心架构设计

### 3.1 整体架构

```
┌───────────────────────────────────────────────────────────┐
│                    QGIS Agent Plugin                       │
│                                                           │
│  ┌─────────────────────┐                                  │
│  │        plugin.py     │ ← QGIS 入口，管理生命周期        │
│  └──────────┬──────────┘                                  │
│             ↓                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  ui/ (UI 层)                                         │  │
│  │  ┌───────────┐ ┌───────────────┐ ┌───────────────┐  │  │
│  │  │ sidebar   │ │ message_widget│ │ tool_card     │  │  │
│  │  └─────┬─────┘ └───────────────┘ └───────────────┘  │  │
│  │        │  ┌──────────────┐                           │  │
│  │        └──│settings_dialog│                           │  │
│  │           └──────────────┘                           │  │
│  └───────────────┬─────────────────────────────────────┘  │
│                  ↓                                        │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  core/ (核心逻辑层)                                   │  │
│  │  ┌──────────────┐  ┌───────────┐                     │  │
│  │  │ agent_engine │→│ llm_client│                     │  │
│  │  └──────┬───────┘  └───────────┘                     │  │
│  │         ↓                                            │  │
│  │  ┌──────────────┐  ┌─────────────┐  ┌─────────────┐ │  │
│  │  │tool_registry │  │ context_mgr │  │ conv_mgr    │ │  │
│  │  └──────┬───────┘  └─────────────┘  └─────────────┘ │  │
│  │         │      ┌─────────────────┐                   │  │
│  │         │      │ file_source_mgr │                   │  │
│  │         │      └─────────────────┘                   │  │
│  └─────────┼───────────────────────────────────────────┘  │
│            ↓                                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  tools/ (GIS 工具层)                                  │  │
│  │  batch_reproject │ batch_clip │ buffer │ ...         │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 3.2 LLM 客户端 (`llm_client.py`)

使用 OpenAI 兼容协议，统一调用接口。

**支持的 Provider：**

| Provider | Base URL | 模型 |
|----------|----------|------|
| DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat, deepseek-coder |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-plus, qwen-turbo, qwen-max |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash, glm-4, glm-4-plus |
| 自定义 | 用户填写 | 用户填写 |

**核心接口：**
- `chat_stream(messages, tools)` — 流式调用，yield 每个 SSE chunk
- `chat(messages, tools)` — 非流式调用，返回完整响应
- Function Calling 优先；不支持的模型回退到 JSON 提取模式

### 3.3 Agent 引擎 (`agent_engine.py`)

核心对话循环：

```
用户输入
  → 收集项目上下文（context_manager）
  → 构建 messages（含 system prompt + 滑动窗口历史）
  → 调用 LLM（llm_client.chat_stream）
    ↓
  LLM 返回 tool_calls
    → Agent 引擎格式校验（图层名存在性、CRS 合法性）
    → 校验通过 → 执行工具（tool_registry.execute）
    → 校验失败 → 返回错误消息给用户
    ↓
  工具执行结果追加到 messages
  → 再次调用 LLM
    ↓
  LLM 返回最终回复 或 继续 tool_calls
  → 最大循环 10 次后强制终止
    ↓
  输出最终结果到侧边栏
```

**关键机制：**
- **滑动窗口**：每次请求只发最近 20 条消息 + 完整 system prompt
- **并发控制**：用户发新消息时打断当前回复（abort SSE + 中止工具）
- **分层校验**：Agent 校验格式 → QGIS Processing 校验业务逻辑

### 3.4 工具注册表 (`tool_registry.py`)

每个工具同时注册为：
1. **Python 函数** — Agent 引擎直接调用
2. **LLM 函数定义** — JSON Schema 格式，传给 LLM 的 function calling

### 3.5 上下文管理器 (`context_manager.py`)

每次 LLM 调用前自动收集项目信息并注入 system prompt：

```json
{
  "layers": [
    {
      "name": "roads",
      "type": "vector",
      "crs": "EPSG:4326",
      "geometry_type": "LineString",
      "feature_count": 1523,
      "fields": ["id", "name", "type"],
      "extent": [116.0, 39.0, 117.0, 40.0]
    }
  ],
  "project_crs": "EPSG:4326",
  "selected_layers": ["roads"],
  "canvas_extent": [116.0, 39.0, 117.0, 40.0]
}
```

### 3.5.1 双源输入机制（`file_source_manager.py`）

**需求：** 用户可通过两种方式提供数据：
1. **源 A（项目图层）**：在 QGIS 中手动加载的图层（现有行为）
2. **源 B（插件文件）**：通过插件侧边栏"添加文件"按钮导入的文件

**决策规则：**
- 仅有源 A → 按现有逻辑处理
- 仅有源 B → 将文件加载为临时图层，然后用工具处理
- 两者都有 → AI 追问用户选择哪种数据源
- 两者都没有 → 提示用户先加载数据

**数据模型：**

```python
class LayerSource(Enum):
    PROJECT = "project"   # QGIS 项目图层
    PLUGIN = "plugin"     # 插件导入的文件

@dataclass
class ManagedFile:
    file_path: str           # 完整路径（仅内部，不传 LLM）
    display_name: str        # 文件名（UI 显示）
    layer_name: str          # QGIS 图层名（含 [plugin] 前缀）
    source: LayerSource
    is_loaded: bool = False
    load_error: Optional[str] = None
    layer_id: Optional[str] = None
```

**临时图层命名：** `[plugin] 文件名`（如 `[plugin] roads`），冲突时追加数字后缀。

**Agent 引擎决策流程：**

```
用户发送消息
  ↓
_resolve_layer_source()
  ├── NO_LAYERS → 提示加载数据，结束
  ├── ASK_USER → 追问用户选择，等待回复
  ├── USE_PLUGIN_FILES → load_all_to_qgis()，继续
  └── USE_PROJECT → 继续（现有逻辑）
  ↓
context_manager.collect_context(source_decision)
  ↓
构建 messages → 调用 LLM → 工具执行 → 返回结果
```

**上下文 JSON 扩展：** 每个 layer 新增 `"source"` 字段（`"project"` 或 `"plugin"`），新增 `"layer_source_summary"` 顶层字段。

**边缘情况：**
- 文件不存在/格式不支持 → 检查扩展名白名单 + `.isValid()`
- 对话中途移除文件 → 从 QGIS 移除临时图层，context 自动更新
- QGIS 中手动删除插件图层 → 监听 `layersRemoved` 信号同步状态
- 新建对话 → 清空文件列表 + 确认是否移除临时图层
- 切换对话 → 从 metadata 恢复文件列表，按需重新加载

### 3.6 对话历史管理 (`conversation_manager.py`)

**数据模型：**
- `Conversation(id, title, created_at, updated_at, messages, metadata)`
- `ConversationSummary(id, title, updated_at, message_count, preview)`

**存储：SQLite**
- 路径：插件数据目录下 `conversations.db`
- 表：`conversations` + `messages`

**标题生成：** 用户首条消息后截取前 20 字作为标题（LLM 异步生成作为 P1 增强）

### 3.7 UI 样式规范

#### 3.7.1 主题策略

插件跟随 QGIS 系统主题，自动适配浅色/深色模式。通过 `QApplication.palette()` 获取当前系统调色板，不硬编码颜色值。

#### 3.7.2 配色方案

颜色从 QGIS 系统调色板动态获取，语义映射如下：

| 语义 | 浅色模式 | 深色模式 | 用途 |
|------|----------|----------|------|
| 主背景 | palette(Window) | palette(Window) | 侧边栏背景 |
| 消息区背景 | palette(Base) | palette(Base) | 消息列表背景 |
| AI 消息背景 | #F5F5F5 | #2D2D2D | AI 消息文本块背景 |
| 用户消息背景 | palette(Highlight) 10% 透明度 | palette(Highlight) 15% 透明度 | 用户消息文本块背景 |
| 主文字 | palette(Text) | palette(Text) | 正文文字 |
| 次要文字 | palette(PlaceholderText) | palette(PlaceholderText) | 时间戳、状态文字 |
| 强调色 | palette(Highlight) | palette(Highlight) | 链接、按钮高亮 |
| 成功色 | #4CAF50 | #66BB6A | 工具执行成功、色条 |
| 错误色 | #F44336 | #EF5350 | 工具执行失败、错误文字 |
| 执行中色 | #2196F3 | #42A5F5 | 工具执行中、spinner |
| 警告色 | #FF9800 | #FFA726 | 确认对话框、警告提示 |

#### 3.7.3 消息列表样式

- **无气泡设计**：消息以文本块展示，不使用圆角气泡
- **AI 消息**：左对齐，浅灰背景（#F5F5F5 / #2D2D2D），圆角 4px，最大宽度为消息区 85%
- **用户消息**：右对齐，主题高亮色浅透明背景，圆角 4px，最大宽度为消息区 85%
- **消息间距**：紧凑模式，消息块之间 8px 间距
- **内边距**：消息块内部 padding 10px 12px
- **字体**：使用 QGIS 系统字体（默认 Segoe UI 9pt / San Francisco / Ubuntu），不硬编码
- **代码块**：等宽字体（Consolas / Monaco / Ubuntu Mono），背景色 palette(Base) 动态获取

#### 3.7.4 工具调用卡片样式

- **布局**：左对齐，左侧 3px 色条 + 轻微背景色
- **色条颜色**：随状态变化
  - 执行中：#2196F3（蓝色）
  - 成功：#4CAF50（绿色）
  - 失败：#F44336（红色）
- **背景色**：AI 消息背景色基础上加深 3%（微弱区分）
- **圆角**：4px
- **内边距**：10px 12px
- **标题行**：工具名（等宽字体）+ 状态图标（spinner/✅/❌）+ 耗时
- **详情区**：默认折叠，点击标题行展开，显示参数 JSON 和输出摘要
- **展开/收起**：带 150ms 过渡动画

#### 3.7.5 输入区样式

- **输入框**：自适应高度（1-5 行），超出后出现滚动条
- **发送按钮**：图标按钮，在输入框右侧
- **文件附件区**：输入框上方，仅在有文件时可见，每个文件标签带 × 删除按钮
- **添加文件按钮**：输入框左侧，📎 图标
- **快捷键**：Enter 发送，Shift+Enter 换行

#### 3.7.6 顶部栏样式

- **布局**：左侧插件名称，右侧按钮组（新对话、历史、设置）
- **按钮**：图标按钮，hover 显示 tooltip
- **分隔线**：底部 1px 边框，颜色 palette(Mid)

#### 3.7.7 历史列表样式

- **列表项**：标题（粗体）+ 预览（次要文字色，单行截断）+ 时间（右对齐）
- **hover 效果**：背景色 palette(Highlight) 5% 透明度
- **删除按钮**：hover 时显示在列表项右侧
- **搜索框**：顶部，placeholder "搜索对话..."

---

## 4. V1 范围边界

### 4.1 P0 — V1 必须交付

| # | 工具 | 函数名 | QGIS 算法 |
|---|------|--------|-----------|
| 1 | 批量坐标转换 | `batch_reproject` | `native:reprojectlayer` |
| 2 | 批量裁剪 | `batch_clip` | `native:clip` |
| 3 | 缓冲区分析 | `buffer` | `native:buffer` |

**V1 P0 功能清单：**
- [x] 插件安装/加载/卸载
- [x] 右侧侧边栏 QDockWidget
- [x] 消息输入/发送/流式回复
- [x] 工具调用卡片（折叠/展开/状态指示）
- [x] 任务进度展示
- [x] DeepSeek API 集成 + function calling
- [x] 3 个核心 GIS 工具
- [x] Agent 引擎（对话循环 + 工具调度）
- [x] 上下文感知（图层列表、CRS）
- [x] 设置对话框（API Key、模型选择）
- [x] 参数分层校验（图层名存在性、CRS 合法性）
- [x] 文件覆盖确认对话框（跨线程信号机制，QEventLoop + signal 桥接）
- [x] 打断当前回复（用户发新消息时）
- [x] 双源输入（添加文件按钮 + 项目图层自动检测 + 冲突追问）
- [x] 对话历史持久化（SQLite）
- [x] 对话历史列表（搜索、删除、切换）
- [x] UI 样式跟随 QGIS 主题（浅色/深色自适应）

### 4.2 P1 — V1.1 迭代

| # | 工具 | 函数名 | QGIS 算法 |
|---|------|--------|-----------|
| 4 | 叠加分析 | `overlay` | `native:intersection/union/difference` |
| 5 | 属性查询 | `attribute_query` | `native:extractbyexpression` |
| 6 | 空间查询 | `spatial_query` | `native:extractbylocation` |
| 7 | 栅格计算 | `raster_calculator` | `native:rastercalc` |
| 8 | 格式转换 | `format_convert` | `gdal:convertformat` |
| 9 | 批量导出 | `batch_export` | `native:savefeatures` |
| 10 | 统计汇总 | `statistics` | `native:statisticsbycategories` |

**V1.1 功能清单：**
- [ ] 通义千问和智谱 API 集成（llm_client.py 已预留配置，待测试验证）
- [ ] 自定义 Provider 支持（settings_dialog.py 已支持 UI，待测试验证）
- [x] 对话历史持久化（SQLite）— 已提升至 P0 并完成
- [x] 对话历史列表（搜索、删除、切换）— 已提升至 P0 并完成
- [ ] LLM 自动生成对话标题（当前 fallback 到首条消息截取）
- [ ] 工具卡片撤销按钮
- [ ] 本地日志文件 + 调试模式
- [ ] 首次使用隐私弹窗
- [ ] 中英文国际化
- [ ] 侧边栏拖拽
- [ ] Markdown 渲染增强（表格、链接）
- [ ] 各工具高级参数（overlay、attribute_query 等 7 个工具）
- [x] 文件覆盖确认对话框（跨线程信号机制）— 已提升至 P0 并完成
- [ ] 单元测试 + 端到端测试

### 4.3 明确排除（不做）

- 图片/截图上传
- 自定义工具脚本
- 语音输入
- 多 Agent 协作
- 离线模型
- QGIS Server 支持

---

## 5. 实施步骤

### Phase 1: 项目骨架 + LLM 客户端

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1 | `metadata.txt` | 插件元数据（qgisMinimumVersion=4.0） |
| 2 | `__init__.py` + `plugin.py` | classFactory 入口 + 插件生命周期（initGui/unload） |
| 3 | `core/llm_client.py` | OpenAI 兼容协议、SSE 流式解析、多 Provider、function calling |
| 4 | `ui/settings_dialog.py` | API Key 输入、Provider/Model 选择、测试连接 |
| 5 | `resources.qrc` + `icon.png` | 资源文件 |

**验收：** 插件可在 QGIS 中加载，设置对话框可配置 API Key，发送测试消息收到回复。

### Phase 2: 侧边栏 UI

| 步骤 | 文件 | 内容 |
|------|------|------|
| 6 | `ui/sidebar.py` | QDockWidget 主框架、消息列表 QScrollArea、输入框、顶部栏按钮、文件附件区 |
| 7 | `ui/message_widget.py` | 用户消息气泡（右对齐）、AI 消息气泡（左对齐） |
| 8 | `ui/tool_card.py` | 可折叠工具卡片（spinner/成功/失败状态） |
| 9 | — | 流式文本实时追加显示 |

**验收：** 侧边栏右侧显示，消息输入发送正常，AI 回复流式显示，工具卡片可折叠展开。

### Phase 3: 工具注册表 + 上下文管理 + 文件源管理

| 步骤 | 文件 | 内容 |
|------|------|------|
| 10 | `core/tool_registry.py` | 3 个核心工具的 JSON Schema 定义 + Python 函数映射 |
| 11 | `core/context_manager.py` | 项目图层信息收集（名称、类型、CRS、字段、要素数），支持 source 过滤 |
| 12 | `core/file_source_manager.py` | 文件源管理、临时图层加载/卸载、QGIS 信号监听 |

**验收：** 工具定义正确注入 LLM，上下文信息准确反映项目状态，文件源管理器可正确加载/卸载临时图层。

### Phase 4: 3 个核心 GIS 工具

| 步骤 | 文件 | 内容 |
|------|------|------|
| 13 | `tools/batch_reproject.py` | 批量坐标转换（native:reprojectlayer） |
| 14 | `tools/batch_clip.py` | 批量裁剪（native:clip） |
| 15 | `tools/buffer.py` | 缓冲区分析（native:buffer） |

**验收：** 3 个工具均可通过 Processing.run() 正确执行，返回正确结果。

### Phase 5: Agent 引擎

| 步骤 | 文件 | 内容 |
|------|------|------|
| 16 | `core/agent_engine.py` | 对话循环、tool_calls 解析、工具执行、结果反馈、滑动窗口 |
| 17 | — | System Prompt 构建 + 上下文注入（含数据来源说明） |
| 18 | `core/agent_engine.py` + `core/tool_registry.py` + `tools/batch_reproject.py` | 用户确认机制（跨线程信号 + QEventLoop 阻塞，文件覆盖确认对话框） |
| 19 | — | 打断机制（abort SSE + 中止工具） |
| 20 | — | 双源决策逻辑（`_resolve_layer_source()`：NO_LAYERS / ASK_USER / USE_PROJECT / USE_PLUGIN_FILES） |

**验收：** 端到端链路打通 — 用户输入自然语言 → AI 理解意图 → 调用工具 → 返回结果。双源输入场景（仅项目图层/仅插件文件/两者都有）均正确处理。

### Phase 6: 对话历史 + 测试

| 步骤 | 文件 | 内容 |
|------|------|------|
| 21 | `core/conversation_manager.py` | SQLite 存储、对话 CRUD、自动保存、plugin_files 持久化 |
| 22 | `ui/sidebar.py` (更新) | 历史列表视图、搜索、切换、删除 |
| 23 | `tests/` | 单元测试（LLM mock、工具测试、引擎测试、文件源管理测试） |
| 24 | — | 端到端测试 |

**验收：** 对话历史可保存/切换/删除，单元测试通过，端到端场景验证通过。

---

## 6. 关键文件依赖关系

```
__init__.py
  └── plugin.py
        ├── ui/sidebar.py
        │     ├── ui/message_widget.py
        │     ├── ui/tool_card.py
        │     ├── ui/settings_dialog.py
        │     │     └── core/llm_client.py
        │     ├── core/agent_engine.py
        │     │     ├── core/llm_client.py
        │     │     ├── core/tool_registry.py
        │     │     │     └── tools/*.py
        │     │     ├── core/context_manager.py
        │     │     └── core/file_source_manager.py
        │     └── core/conversation_manager.py
        └── core/llm_client.py
```

---

## 7. System Prompt 设计

```
你是 QGIS Agent，一个专业的 GIS 助手。你运行在 QGIS 4.0 中。

## 你的能力
你可以调用以下 GIS 工具来帮助用户完成空间数据处理任务：
{tool_definitions_json}

## 当前项目状态
{project_context_json}

## 数据来源说明
{data_source_description}

## 工作方式
1. 理解用户的自然语言需求
2. 如果需求复杂，拆解为多个子任务
3. 逐步调用工具完成每个子任务
4. 向用户报告执行结果

## 规则
- 调用工具时，图层名称必须与项目中已有图层的名称完全匹配
- 批量操作前先告知用户将处理多少个图层
- 涉及文件覆盖或删除时，先询问用户确认
- 如果用户的需求超出你的工具范围，坦诚告知并建议替代方案
- 优先使用中文回复（如果用户使用中文）
- 图层名以 "[plugin] " 开头的，是用户通过插件导入的文件，已自动加载为临时图层
- 临时图层在对话结束后可能被清理，处理完成后提醒用户是否需要持久保存
```

---

## 8. 非功能需求

### 8.1 性能

| 指标 | 目标 |
|------|------|
| 插件加载时间 | < 2 秒 |
| 首 token 响应 | < 3 秒（取决于 API） |
| 工具执行 | 后台线程，不阻塞 QGIS UI |
| 100 图层批量操作 | < 5 分钟 |
| 侧边栏内存占用 | < 100MB |

### 8.2 稳定性

| 指标 | 目标 |
|------|------|
| Agent 循环上限 | 10 次自动终止 |
| 工具执行超时 | 5 分钟自动终止 |
| 崩溃隔离 | 全局 try-except，不导致 QGIS 崩溃 |
| API Key 安全 | 不写入日志或错误报告 |

### 8.3 安全性

| 措施 | 说明 |
|------|------|
| API Key 存储 | QgsSettings 本地存储，不写入项目文件 |
| API Key 保护 | 不出现在对话内容中 |
| 路径脱敏 | 不向 LLM 发送完整文件路径，仅发送图层名 |
| 隐私提示 | 设置对话框底部提示"内容将发送到第三方 AI 服务" |

### 8.4 兼容性

| 平台 | 优先级 |
|------|--------|
| Windows 10/11 | P0 |
| macOS (Intel/Apple Silicon) | P1 |
| Ubuntu 22.04+ | P1 |

---

## 9. 验证方案

### 9.1 单元测试

| 测试对象 | 测试内容 |
|----------|----------|
| `llm_client` | mock API 响应，验证请求格式、流式解析、错误处理 |
| `agent_engine` | mock LLM 响应，验证 tool_calls 解析、工具调度、循环控制、双源决策逻辑 |
| `tool_registry` | 验证工具定义 JSON Schema 正确性 |
| `context_manager` | 验证项目上下文收集准确性、source 过滤功能 |
| `file_source_manager` | 验证文件添加/移除、临时图层加载/卸载、QGIS 信号同步 |
| `tools/*` | 创建测试 shapefile，验证每个工具输入输出 |

### 9.2 端到端测试

| 场景 | 输入 | 预期 |
|------|------|------|
| 单图层坐标转换 | "把 roads 转成 3857" | roads_3857 图层添加到项目 |
| 批量坐标转换 | "把所有图层转成 4490" | 所有图层各生成 _4490 新图层 |
| 批量裁剪 | "用 boundary 裁剪所有图层" | 所有图层各生成 _clipped 新图层 |
| 缓冲区分析 | "在 roads 周围做 500 米缓冲区" | roads_buffer_500 图层 |
| 复合任务 | "先裁剪再转坐标系" | 2 步依次执行 |
| 错误处理 | "把不存在的图层转成 4326" | 提示图层不存在 |
| 模糊需求 | "帮我处理一下数据" | AI 追问具体需求 |
| 双源输入-仅文件 | 添加 roads.shp，无项目图层，输入"转成 3857" | 文件加载为临时图层，执行转换 |
| 双源输入-两者都有 | 添加文件 + 项目有图层，输入"转成 3857" | AI 追问使用哪种数据源 |
| 双源输入-移除文件 | 添加文件后点击×删除 | 文件从列表和 QGIS 中移除 |

### 9.3 多模型测试

在 DeepSeek / 通义千问 / 智谱 之间切换，验证均能正常对话和调用工具。

---

## 10. 技术风险与应对

| 风险 | 应对 |
|------|------|
| 部分模型不支持原生 function calling | 回退到 JSON 提取模式，在 system prompt 中要求 LLM 输出 JSON 格式的工具调用 |
| QGIS 4.0 未发布，API 可能变化 | 使用 `qgis.PyQt` 兼容层，避免直接使用 PyQt6；关注 QGIS RFC |
| SSE 流式解析在 Windows 上的兼容性 | 使用 `requests` 的 `iter_lines()` 而非 `httpx` |
| 大图层批量处理耗时 | 使用 QThread + Worker 模式异步执行，UI 显示进度条 |
| LLM 幻觉（不存在的图层名、无效 CRS） | Agent 引擎层做格式校验，不合法参数不调用工具 |
| 长对话 token 消耗过大 | 滑动窗口策略，每次只发最近 20 条消息 |
| 大文件加载到 QGIS 可能导致内存占用过高 | 使用 QgsTask 异步加载，加载期间禁用发送按钮，提供进度反馈 |
| 用户在对话中途移除文件导致工具执行失败 | Agent 引擎捕获异常，提示用户文件已移除，建议重新添加 |
