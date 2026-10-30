# wAgent

基于 OpenAI 兼容接口（默认 DeepSeek）的**流式对话 + 工具调用** Agent。
代码按 **core（业务内核）+ tui（终端界面）** 分层，核心逻辑不依赖任何具体界面，
便于后续扩展 Web / Desktop 等其他前端。

---

## 目录结构

```
wAgent/
├── main.py                    # 组合根：装配 core 与 tui
├── config.example.ini         # 配置模板
├── requirements.txt           # openai + textual + trafilatura
├── core/                      # 业务内核（无 UI 依赖）
│   ├── __init__.py
│   ├── cancellation.py        # CancellationToken（Esc 中断）
│   ├── config.py              # 配置加载 (LLMConfig / load_config)
│   ├── events.py              # 供所有前端消费的 Agent 事件
│   ├── llm.py                 # ChatModel 端口 + OpenAI 适配器
│   ├── agent.py               # 对话状态与工具调用循环
│   ├── skills.py              # Agent Skills 发现与按需加载（loadSkill）
│   └── tools/
│       ├── __init__.py        # build_default_registry()
│       ├── base.py            # ToolSpec / ToolRegistry
│       ├── basic.py           # 日期、闰年、工作目录
│       ├── cli.py             # RunCli：以当前用户权限执行本地命令行程序
│       ├── filesystem.py      # 文件/目录读写与增删改
│       ├── search.py          # 百度搜索 web_search 联网搜索
│       ├── web.py             # curl 抓取网页 + trafilatura 提取 Markdown
│       └── helpers.py         # 路径、编码、文本判定等公共能力
└── tui/                       # Textual 终端界面
    ├── __init__.py
    ├── app.py                 # AgentTUI：布局、事件映射、会话统计
    ├── help_screen.py         # F1 帮助弹窗（命令 / 快捷键）
    ├── widgets.py             # 消息 / 可折叠工具卡片 / 提示控件
    └── styles.tcss            # 界面样式
```

**依赖方向：`tui -> core`，`core` 从不反向依赖 `tui`。**
`main.py` 是唯一的组合根，负责创建配置、模型、工具注册表和 Agent，再注入 UI。

---

## 分层设计

| 层 | 模块 | 职责 |
| --- | --- | --- |
| 展示层 | `tui/*` | 输入、流式渲染、工具调用展示、状态栏；只消费事件 |
| 应用层 | `core/agent.py` | 维护消息历史，驱动「流式回复 → 工具调用 → 再次请求」循环 |
| 事件层 | `core/events.py` | `TextDelta` / `ToolCallStarted` / `ToolCallFinished` / `TurnCompleted` / `TurnCancelled` / `AgentError` |
| 传输层 | `core/llm.py` | `ChatModel` 协议与 OpenAI 兼容实现，屏蔽具体 SDK |
| 工具层 | `core/tools/` | `ToolSpec` 自带 JSON Schema 与实现，`ToolRegistry` 负责注册/路由 |
| 配置层 | `core/config.py` | 读取 `config.ini`，与 UI 无关 |

### 事件流

```
User ──send(text)──> Agent
                      │
          yield TextDelta        ──> 前端追加到当前助手消息
          yield ToolCallStarted  ──> 前端显示工具调用
          yield ToolCallFinished ──> 前端填充工具结果
          yield TurnCompleted    ──> 前端结束本轮
          yield TurnCancelled    ──> 用户中断，本轮从历史中移除
          yield AgentError       ──> 前端显示错误
```

任何前端只需迭代 `agent.send(text)` 并按事件类型渲染，无需了解 OpenAI 或工具细节。
需要中断时，把 `CancellationToken` 传给 `send(text, cancel=token)`，并在另一个线程调用
`token.cancel()`；Agent 会在下一个流式分片处停止。取消或失败的一轮不会写入历史。

---

## 运行

```bash
cd Agent/wAgent
pip install -r requirements.txt
copy config.example.ini config.ini   # Windows；Linux/macOS 用 cp
# 编辑 config.ini，填入 [llm] api_key 和 [search] baiduqianfan_api_key
python main.py
```

> `fetchWeb` 通过系统 `curl` 抓取网页（Windows 10+ 已自带），并用 `trafilatura`
> 提取正文；如需使用该工具，请确保 `curl` 位于 `PATH` 中。静态 HTML 无法提取正文或
> 正文过短时，会自动尝试调用本机 Edge / Chrome 无头浏览器渲染页面，以支持 JavaScript 动态内容。

> `RunCli` 可执行本机任意已安装的命令行程序（如 `git`、`python`、`pip`）。
> 它用 `subprocess` + `shell=False` 直接执行程序，参数以列表传递，不解析管道、
> 重定向等 Shell 语法；命令以运行 wAgent 的当前用户权限执行。工具会返回标准输出、
> 标准错误和退出码，默认超时 30 秒，单个输出流超过 8000 字符时会被截断并标注。
> 该工具仅用于受控教学实验环境，当前阶段不提供命令白名单或审批机制。

> `searchweb` 使用百度搜索 `web_search` 接口；请在 `config.ini` 的 `[search]`
> 段配置 `baiduqianfan_api_key`，API 地址可通过 `base_url` 覆盖。
> 该接口只需 API Key，无需 `appid`；返回每条结果的摘要、标题和 URL。

`config.ini` 已被 `.gitignore` 忽略。也可通过环境变量指定配置位置：

```bash
set WAGENT_CONFIG=D:\path\to\config.ini   # Windows
```

### TUI 界面

- 顶部信息栏：应用名、工具数量、模型、工作目录和快捷键提示。
- 会话区：用户 / 助手消息使用彩色左边条；工具调用是可点击展开的卡片，
  展开后显示参数 JSON、执行结果与耗时。
- 右侧栏：会话信息（模型、接口、目录、会话 ID、轮次、消息数、单轮上限、状态）
  与全部已注册工具；`Ctrl+B` 显示 / 隐藏。
- 底部状态栏：状态、轮次、工具调用次数、耗时和 `Esc 中断` 提示。

### TUI 操作

| 操作 | 说明 |
| --- | --- |
| `Enter` | 发送消息 |
| `Esc` | 中断当前生成（已完成的问答才会写入历史） |
| `F1` / `F2` | 打开帮助弹窗（VSCode 中 F1 可能被占用，可用 F2） |
| `Ctrl+B` | 显示 / 隐藏右侧栏 |
| `Ctrl+N` | 新建会话（重置历史） |
| `Ctrl+L` | 清屏（保留历史） |
| `Ctrl+X` | 退出（避开 VSCode 的 `Ctrl+Q` 快捷键） |
| `/help` | 打开帮助 |
| `/clear` | 清空界面，保留历史 |
| `/new` | 新建会话，重置历史 |
| `/tools` | 列出已注册工具 |
| `/cwd` | 显示工作目录 |
| `/model` | 显示模型与接口 |
| `/quit` | 退出 |

> 普通字母键（如 `q`）只会输入到输入框，不会触发退出；退出请用 `Ctrl+X` 或 `/quit`。
> 请务必在**可交互的终端**中运行（VSCode 的「终端」面板或 Windows Terminal），
> 不要用 Code Runner 等输出到「输出」面板的方式启动，否则 TUI 无法接收键盘输入。

---

## Agent Skills

wAgent 启动时会以**程序启动时的工作目录**为项目根目录，扫描
`.agents/skills/` 下的技能目录。每个技能目录必须包含 `SKILL.md`，其开头使用
YAML Frontmatter 声明 `name` 和 `description`：

```markdown
---
name: example-skill
description: 用一句话说明这个技能能做什么。
---

这里是技能的完整说明，只会在 LLM 调用 `loadSkill` 时加载。
```

初始化阶段只读取 Frontmatter 中的 `name` 和 `description` 并注入 System Prompt，
不会把 `SKILL.md` 正文放进上下文。LLM 需要时调用 `loadSkill`：

- `{"name": "example-skill"}`：返回 `SKILL.md` 全文。
- `{"name": "example-skill", "filename": "references/guide.md"}`：读取技能目录内的附件。

`filename` 支持相对于技能目录的路径、项目相对路径和绝对路径；只提供文件名时会
递归搜索技能目录，重名时返回候选路径。所有读取都被限制在该技能目录内部。

---

## 扩展指南

### 新增工具

1. 在 `core/tools/` 下新增实现函数，失败返回提示字符串、成功返回结果字符串。
2. 用 `ToolSpec(name, description, parameters, handler)` 描述工具。
3. 加入 `BASIC_TOOLS` / `FILESYSTEM_TOOLS` / `WEB_TOOLS` / `build_search_tools()`，或在组合根向 `ToolRegistry` 注册。

Agent 和 UI 均无需修改。

### 新增前端（Web / Desktop）

复用 `core`，实现一个遍历 `Agent.send()` 事件的视图即可：

```python
for event in agent.send(user_text):
    if isinstance(event, TextDelta):
        ...
    elif isinstance(event, ToolCallFinished):
        ...
```

若需要替换模型供应商，实现 `core.llm.ChatModel` 协议的 `stream()` 方法，
并在组合根注入新的适配器。
