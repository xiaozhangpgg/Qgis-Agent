CLAUDE.md

  本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。
  注意：
  1.在为本项目工作时，所有回答得用中文
  2.开发时必须参考QGIS API 文档：https://qgis.org/pyqgis/3.44/

  项目概述

  QGIS Agent 是一个 QGIS 3.28+ 插件，提供 AI 驱动的侧边栏助手。用户用自然语言描述 GIS 操作，Agent 通过 LLM 函数调用来执行 QGIS Processing 算法。

  架构

  插件采用分层架构：

  用户输入 → SidebarWidget → AgentEngine → LLMClient (SSE 流式)
                                              ↓
                                        tool_calls (JSON)
                                              ↓
                                     ToolRegistry.execute()
                                              ↓
                                    QGIS Processing 算法
                                              ↓
                                         结果 → LLM → 用户

  核心层 (core/)：
  - agent_engine.py — 在后台 QThread 中编排 LLM ↔ 工具循环（最多 10 次迭代）。每次迭代重新构建包含项目上下文和工具定义的系统提示词。
  - llm_client.py — 兼容 OpenAI 的 HTTP 客户端，支持 SSE 流式传输和函数调用。支持 DeepSeek、通义千问、智谱和自定义提供商。
  - tool_registry.py — 将工具名映射到 Python 函数 + JSON Schema 定义。TOOL_DEFINITIONS 列表包含发送给 LLM 的所有 Schema。
  - context_manager.py — 收集 QGIS 项目状态（图层、CRS、字段）用于系统提示词注入。
  - conversation_manager.py — 对话历史的 SQLite 持久化。
  - file_source_manager.py — 管理双数据源：项目图层 vs 插件导入的文件。

  工具层 (tools/)：
  每个工具是一个独立模块，包含 run_xxx() 函数：
  1. 验证输入（图层存在性、CRS 有效性）
  2. 调用 processing.run() 执行 QGIS 原生算法
  3. 返回 {"success": bool, "message": str, "results": [...]}

  UI 层 (ui/)：
  - sidebar.py — 主 QDockWidget，包含聊天界面、历史视图、文件附件
  - message_widget.py — 用户/AI 消息气泡组件
  - tool_card.py — 可折叠卡片，显示工具执行状态
  - settings_dialog.py — LLM 提供商配置对话框

  关键模式

  - 所有 LLM 调用和工具执行都在 _WorkerThread（后台 QThread）中进行，绝不在主线程执行
  - 工具函数通过 ToolRegistry.execute() 注入 _confirm_callback 和 _ask_dir_callback，用于用户确认（文件覆盖、目录选择）
  - 图层查找通过 tools/_utils.find_layer() 进行名称匹配——提供大小写不敏感的变体
  - 插件导入的文件在图层名前加 [plugin]  前缀，并设置 qgis_agent_source 自定义属性
  - 系统提示词在每次 Agent 循环迭代时用最新的项目上下文重新构建

  添加新工具

  1. 在 tools/ 下创建 new_tool.py，实现 run_new_tool() 函数
  2. 在 tools/__init__.py 中导出
  3. 在 core/tool_registry.py 的 TOOL_DEFINITIONS 中添加 JSON Schema
  4. 在 core/agent_engine.py 的 AgentEngine._register_tools() 中注册

  开发环境

  - QGIS 3.28+（目标版本 3.44）— 插件运行在 QGIS 内置的 Python 中
  - Python 3.9+，使用 PyQt5（通过 qgis.PyQt 兼容层）
  - 外部依赖：requests（用于 LLM API 调用）
  - QGIS API 文档：https://qgis.org/pyqgis/3.44/

  运行与测试

  - 安装：将文件夹复制到 QGIS 插件目录（详见 README.md 中的平台路径）
  - 调试：QGIS 消息日志面板 → "QgisAgent" 标签（在 __init__.py 中通过 QgsMessageLogHandler 配置）
  - 无测试套件 — tests/ 已加入 gitignore；目前没有测试基础设施

  约定

  - 日志：使用 logging.getLogger("QgisAgent") — 输出到 QGIS 消息日志
  - 所有面向用户的字符串使用中文
  - 工具返回格式：{"success": bool, "message": str, "error": str, "results": list}
  - CRS 处理：缓冲区工具在分析前会自动将地理坐标系重投影到投影坐标系（UTM）

  开发工作流（计划→审查→执行）

  当用户提出修 bug、开发功能或修改功能时，严格遵循以下三阶段流程：

  阶段一：计划
  1. 分析需求，理解涉及的代码范围
  2. 将任务拆解为子任务，写入计划文档 docs/plan_日期_功能名.md
  3. 计划文档包含：
     - 整体方案概述
     - 子任务拆分（数量视复杂度而定）
     - 每个子任务的负责范围、涉及文件、具体要做的事
     - 子任务之间的依赖关系（并行 or 串行）
  4. 告知用户计划已就绪，等待审查

  阶段二：审查
  用户审查计划，提出修改意见或确认通过。

  阶段三：执行
  1. 用户确认后，调度子 agent（model: mimo-2.5）执行各子任务
  2. 无依赖关系的子任务并行执行，有依赖的串行执行
  3. 主 agent（当前模型）负责代码审查：
     - 检查子 agent 产出的质量、一致性、是否符合项目规范
     - 发现问题直接修改，不写审查意见让用户决定
  4. 全部完成后向用户汇报结果