# Practice02 — 基于 OpenAI 兼容接口的工具调用（Function Calling）Agent

本项目是一个命令行交互式 Agent 示例，通过 OpenAI 兼容接口（默认 DeepSeek）实现 **流式对话 + 函数调用（Function Calling）**。
Agent 除了能正常对话外，还能自主调用一组内置工具，完成**日期时间获取、闰年判断、工作目录查询、目录列举、文件类型识别、纯文本读取、文件创建/编辑、目录创建/删除、文件删除、重命名**等本地文件系统操作。

> 架构图见 [chat3_architecture.mmd](chat3_architecture.mmd)（Mermaid 格式纯文本）。

---

## 目录结构

```
practice02/
├── chat.py                    # 早期版本：基础对话
├── chat2.py                   # 中间版本：流式对话
├── chat3.py                   # 当前主程序：流式对话 + 工具调用（本文档重点）
├── chat3_architecture.mmd     # chat3.py 的 Mermaid 代码架构图
├── config.ini                 # 大模型配置（已 gitignore，需自行创建）
├── requirements.txt           # 依赖：openai
└── README.md
```

---

## 环境准备

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

`requirements.txt` 内容：

```
openai
```

### 2. 创建配置文件 `config.ini`

`config.ini` 已被加入 `.gitignore`，请自行在项目根目录创建，内容格式如下：

```ini
[llm]
base_url = https://api.deepseek.com/v1
model_name = deepseek-chat
api_key = 你的 API Key
```

程序在启动时通过 `configparser` 读取该文件中的 `[llm]` 段：

| 配置项       | 说明                                        |
| ------------ | ------------------------------------------- |
| `base_url`   | OpenAI 兼容接口地址（如 DeepSeek、Ollama 等） |
| `model_name` | 模型名称，例如 `deepseek-chat`              |
| `api_key`    | 接口密钥                                    |

### 3. 运行

```bash
python chat3.py
```

出现提示后输入问题即可，按 `Ctrl+C` 或 `Ctrl+D`（EOF）退出。

---

## 核心架构

`chat3.py` 采用**分层设计**，自上而下分为六层：

| 层次 | 主要组件 | 职责 |
| --- | --- | --- |
| 配置层 | `config.ini` / `configparser` / `OpenAI` 客户端 | 读取 LLM 配置并初始化客户端 |
| 主循环层 | `messages` 列表 + 交互 `while` 循环 | 读取用户输入、维护对话上下文、驱动工具调用循环 |
| LLM 流式交互层 | `stream_reply(messages)` | 流式接收回复，边收边打印，并拼装 `tool_calls` |
| 工具定义层 | `TOOLS` 列表 | 以 JSON Schema 描述工具签名，供模型选择 |
| 工具调度层 | `call_tool(name, arguments)` | 解析参数并按工具名路由到具体实现 |
| 工具实现层 + 公共辅助层 | 各 `create_file` / `edit_file` … 及 `resolve_path` / `looks_like_text` / `read_text` / `run_command` | 真正执行文件系统操作，并复用公共能力 |

### 交互流程

1. 用户输入问题 → 以 `role=user` 追加到 `messages`。
2. 调用 `stream_reply(messages)`，向模型发起**流式**请求，并带上 `tools=TOOLS`。
3. 流式解析返回的 `delta`：
   - `delta.content` → 累加 `reply` 并实时打印；
   - `delta.tool_calls` → 按 `index` 拼接工具调用的 `id` / `name` / `arguments`。
4. 若**无**工具调用：将 `reply` 以 `role=assistant` 追加到消息列表，本轮结束，等待下一次输入。
5. 若**有**工具调用：
   - 将带 `tool_calls` 的 `assistant` 消息追加到上下文；
   - 逐个执行 `call_tool(name, arguments)`，打印调用与返回；
   - 每个结果以 `role=tool` + `tool_call_id` 追加到上下文；
   - **回到第 2 步**继续请求模型，直到模型不再请求工具为止（支持多轮连续工具调用）。

### 关键特性

- **流式输出**：正文边生成边打印，工具调用参数则增量拼接后再执行。
- **多轮工具链**：一次用户提问可触发多次工具调用与模型往返。
- **工具名安全路由**：未知工具名返回 `未知工具: xxx`，不会抛异常中断会话。
- **统一错误返回**：所有工具失败时返回中文提示字符串（而非抛异常），保证 Agent 可继续对话。
- **多编码兼容**：读写文件时依次尝试 `utf-8-sig` / `gbk` / 系统首选编码 / `utf-8`，减少乱码。
- **文本文件安全判定**：先看扩展名白/黑名单，再看 MIME 类型，最后采样文件头判断是否含 NUL 与控制字符。
- **路径规范化**：`resolve_path` 支持 `~` 展开、相对路径基于当前工作目录、最终统一为绝对路径。

---

## 内置工具一览

工具定义在 `TOOLS`（JSON Schema），实现在同名 Python 函数中，经 `call_tool` 路由调用。

### 基础类

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `getDate` | — | 获取当前日期时间（Windows 走 `cmd /c date /t` + `time /t`，其他平台走 `date +%Y-%m-%d %H:%M:%S`） |
| `isLeapYear` | `year: int` | 判断是否闰年 |
| `getCwd` | — | 获取当前工作目录绝对路径 |

### 读取类

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `listDirectory` | `path?: str` | 列出目录内容，目录优先排序，附文件字节数 |
| `getFileType` | `path: str` | 返回扩展名、MIME 类型、是否为纯文本 |
| `readTextFile` | `path: str` | 读取纯文本文件；非文本文件拒绝读取 |

### 写入类

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `createFile` | `directory: str`, `filename: str`, `content?: str` | 新建文件，**已存在则不覆盖**；`filename` 不可含路径 |
| `editFile` | `path: str`, `content: str`, `mode?: overwrite\|append\|replace`, `old_text?: str` | 支持整体覆盖 / 追加 / 首次替换 |

### 目录管理类

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `createDirectory` | `path: str` | 递归创建多级目录 |
| `deleteDirectory` | `path: str` | 递归删除非空目录 |

### 删除与重命名类

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `deleteFile` | `path: str` | 删除文件（目录请用 `deleteDirectory`） |
| `renameFileOrDirectory` | `path: str`, `new_name: str` | 同目录内重命名，`new_name` 不可含路径 |

---

## 安全约束

`chat3.py` 在实现工具时内置了一些保护措施，避免模型误操作：

- `deleteDirectory` 拒绝删除**根目录**，以及**当前工作目录及其上级目录**。
- `renameFileOrDirectory` 拒绝重命名根目录；`new_name` 不允许包含路径分隔符。
- `createFile` 的 `filename` 不允许包含路径，且**不覆盖已存在的文件**。
- `readTextFile` / `editFile` 仅作用于**纯文本文件**，二进制文件（如图片、压缩包、可执行文件）一律拒绝。
- 所有路径均经过 `resolve_path` 规范化为绝对路径后再操作。

> ⚠️ 提示：工具具备真实文件系统读写与删除能力，请仅在受控目录内使用，并注意 `config.ini` 中的密钥已被 `.gitignore` 排除。

---

## 常量和辅助模块

| 名称 | 作用 |
| --- | --- |
| `TEXT_EXTENSIONS` | 常见纯文本扩展名白名单（`.py`、`.md`、`.json`、`.yaml` …） |
| `BINARY_EXTENSIONS` | 常见二进制扩展名黑名单（`.png`、`.zip`、`.exe` …） |
| `run_command(cmd)` | 执行子命令并按多编码尝试解码输出 |
| `resolve_path(path)` | `~` 展开、相对路径转绝对路径 |
| `looks_like_text(path)` | 扩展名 + MIME + 采样控制字符比例判定是否纯文本 |
| `read_text(path)` | 多编码逐级尝试读取文本内容 |

---

## 扩展新的工具

1. 在 `TOOLS` 中追加一个 `{"type": "function", "function": {...}}` 描述（含 `name`、`description`、`parameters`）。
2. 在文件底部实现对应的 Python 函数，保持"失败返回提示字符串、成功返回结果字符串"的约定。
3. 在 `call_tool` 中增加一条 `if name == "你的工具": return 你的函数(...)` 路由。

无需修改主循环与 `stream_reply`，模型即可自动发现并按需调用新工具。
