# QGIS Agent

<p align="center">
  <strong>AI 驱动的 QGIS 智能助手 — 用自然语言完成 GIS 操作</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/QGIS-3.28%2B-green?logo=qgis" alt="QGIS">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/version-1.1.0-orange" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
</p>

---

## ✨ 特性

- 🗣️ **自然语言驱动** — 用一句话描述需求，AI 自动拆解任务并调用 QGIS 工具执行
- 🤖 **多模型支持** — DeepSeek / 通义千问 / 智谱 / 任意 OpenAI 兼容 API
- 🔄 **流式响应** — SSE 实时输出，工具调用卡片展示执行状态
- 📂 **双数据源** — 支持 QGIS 项目图层和插件文件导入两种数据来源
- 💬 **对话历史** — SQLite 持久化存储，支持搜索、切换、删除
- 🛡️ **安全确认** — 文件覆盖等危险操作弹出确认对话框

## 🛠️ 21 种 GIS 工具

| 工具 | 说明 | QGIS 算法 |
|------|------|-----------|
| 批量坐标转换 | 多图层批量重投影 | `native:reprojectlayer` |
| 批量裁剪 | 用面图层批量裁剪 | `native:clip` |
| 缓冲区分析 | 创建缓冲区（自动处理地理坐标系） | `native:buffer` |
| 叠加分析 | 交集/并集/差集 | `native:intersection/union/difference` |
| 对称差异 | 两个图层的对称差异区域 | `native:symmetricaldifference` |
| 属性查询 | QGIS 表达式筛选要素 | `native:extractbyexpression` |
| 空间查询 | 空间关系筛选要素 | `native:extractbylocation` |
| 范围提取 | 按矩形范围提取要素 | `native:extractbyextent` |
| 栅格计算器 | 栅格代数运算 | `native:rastercalc` |
| 格式转换 | 矢量/栅格多格式导出 | `native:savefeatures` |
| 批量导出 | 多图层批量导出文件 | `native:savefeatures` |
| 统计汇总 | 字段统计与分组统计 | `qgis:statisticsbycategories` |
| 字段计算器 | QGIS 表达式计算新字段 | `native:fieldcalculator` |
| 溶解 | 按字段或全部溶解相邻要素 | `native:dissolve` |
| 合并图层 | 多个同类型矢量图层合并 | `native:mergevectorlayers` |
| 质心提取 | 提取面/线要素的几何质心 | `native:centroids` |
| 凸包 | 计算要素集的最小凸多边形 | `native:convexhull` |
| 边界提取 | 提取面边界线或线端点 | `native:boundary` |
| 多部件拆分 | 多部件要素拆分为单部件 | `native:multiparttosingleparts` |
| 删除字段 | 删除指定属性字段 | `native:deletecolumn` |
| 重命名字段 | 重命名属性字段 | `native:renametablefield` |

## 📸 截图

> *待补充*

## 📦 安装

### 方式一：手动安装（推荐）

1. 下载或克隆本项目：

```bash
git clone https://github.com/xiaozhangpgg/QgisAgent.git
```

2. 将 `QgisAgent` 文件夹复制到 QGIS 插件目录：

| 平台 | 路径 |
|------|------|
| Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\QgisAgent\` |
| Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/QgisAgent/` |
| macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/QgisAgent/` |

3. 在 QGIS 中启用插件：菜单 → 插件 → 管理和安装插件 → 已安装 → 勾选 **QGIS Agent**

### 方式二：从 ZIP 安装

1. 将项目打包为 ZIP 文件（确保 `metadata.txt` 在 ZIP 根目录）
2. QGIS 菜单 → 插件 → 管理和安装插件 → 从 ZIP 安装

> **注意：从 GitHub 下载 ZIP 常见问题**
>
> GitHub 下载的 ZIP 解压后经常出现**两层嵌套目录**，导致 QGIS 找不到 `metadata.txt`。请按以下步骤操作：
>
> 1. 解压 ZIP 后，打开文件夹，确认 `metadata.txt`、`__init__.py`、`plugin.py` 这三个文件**直接位于当前目录下**（不是在子文件夹里）
> 2. 如果发现多了一层目录（如 `QgisAgent-main/QgisAgent-main/`），请将**内层文件夹**中的所有文件移出
> 3. 确保最终文件夹名为 `QgisAgent`（不带分支后缀），然后将此文件夹复制到 QGIS 插件目录
>
> 正确的目录结构应该是：
> ```
> plugins/QgisAgent/
> ├── metadata.txt      ← 必须在根目录
> ├── __init__.py
> ├── plugin.py
> ├── core/
> ├── tools/
> └── ui/
> ```

## ⚙️ 配置

1. 点击 QGIS 工具栏的 QGIS Agent 图标打开侧边栏
2. 点击 **设置** 按钮
3. 选择 LLM 提供商并填写 API Key：

| 提供商 | Base URL | 推荐模型 |
|--------|----------|----------|
| DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-plus |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash |
| 自定义 | 用户填写 | 用户填写 |

4. 点击 **测试连接** 验证，保存配置

## 🚀 使用

1. 在 QGIS 中加载图层
2. 在侧边栏输入自然语言描述，例如：
   - "把所有图层转成 EPSG:3857"
   - "在 roads 周围创建 500 米缓冲区"
   - "用 admin_boundary 裁剪所有图层"
   - "统计 population 字段的均值和最大值"
3. 可选：点击 📎 按钮添加本地文件作为数据源
4. AI 自动拆解任务 → 调用工具 → 展示结果

## 🏗️ 项目结构

```
QgisAgent/
├── __init__.py              # 插件入口 + 日志配置
├── plugin.py                # QgisAgentPlugin 主类
├── metadata.txt             # QGIS 插件元数据
├── icon.png                 # 插件图标
├── resources.qrc            # Qt 资源文件
├── resources_rc.py          # 编译后资源
│
├── core/                    # 核心引擎层
│   ├── agent_engine.py      # Agent 引擎（LLM + 工具循环）
│   ├── llm_client.py        # LLM 客户端（SSE 流式 + Function Calling）
│   ├── tool_registry.py     # 工具注册表 + JSON Schema
│   ├── context_manager.py   # QGIS 项目上下文收集
│   ├── conversation_manager.py  # 对话历史 SQLite 持久化
│   └── file_source_manager.py   # 双数据源管理
│
├── tools/                   # GIS 工具实现（21 个）
│   ├── _utils.py            # 公共工具函数
│   ├── batch_reproject.py   # 批量坐标转换
│   ├── batch_clip.py        # 批量裁剪
│   ├── buffer.py            # 缓冲区分析
│   ├── overlay.py           # 叠加分析
│   ├── symmetrical_difference.py  # 对称差异
│   ├── attribute_query.py   # 属性查询
│   ├── spatial_query.py     # 空间查询
│   ├── extract_by_extent.py # 范围提取
│   ├── raster_calculator.py # 栅格计算器
│   ├── format_convert.py    # 格式转换
│   ├── batch_export.py      # 批量导出
│   ├── statistics.py        # 统计汇总
│   ├── field_calculator.py  # 字段计算器
│   ├── dissolve.py          # 溶解
│   ├── merge_vector_layers.py  # 合并图层
│   ├── centroids.py         # 质心提取
│   ├── convex_hull.py       # 凸包
│   ├── boundary.py          # 边界提取
│   ├── multipart_to_singleparts.py  # 多部件拆分
│   ├── delete_fields.py     # 删除字段
│   └── rename_field.py      # 重命名字段
│
├── ui/                      # UI 组件
│   ├── sidebar.py           # 侧边栏主界面
│   ├── message_widget.py    # 消息气泡组件
│   ├── settings_dialog.py   # 设置对话框
│   └── tool_card.py         # 工具调用卡片
│
└── docs/                    # 文档
    ├── Code_Wiki.md         # 代码百科
    ├── Development_Plan.md  # 开发计划
    └── PRD_Acceptance_Criteria.md  # PRD 验收标准
```

## 🧩 架构

```
用户输入 → AgentEngine → LLM (Function Calling)
                              ↓
                         tool_calls
                              ↓
                     ToolRegistry.execute()
                              ↓
                    QGIS Processing 算法
                              ↓
                        结果返回 LLM
                              ↓
                       最终回复用户
```

## 🔧 开发

### 环境要求

- QGIS 3.28+（目标版本 3.44）
- Python 3.9+（QGIS 内置）
- PyQt5（通过 `qgis.PyQt` 兼容层使用）

### 调试

- 日志输出：QGIS 消息日志面板 → "QgisAgent" 标签
- API 文档：https://qgis.org/pyqgis/3.44/

### 添加新工具

1. 在 `tools/` 下创建工具文件，实现 `run_xxx()` 函数
2. 在 `tools/__init__.py` 中导出函数
3. 在 `core/tool_registry.py` 的 `TOOL_DEFINITIONS` 中添加 JSON Schema
4. 在 `core/agent_engine.py` 的 `_register_tools()` 中注册

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

- Issue Tracker: https://github.com/xiaozhangpgg/QgisAgent/issues
- Source Code: https://github.com/xiaozhangpgg/QgisAgent
