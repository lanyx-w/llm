# Practice01 - 最简流式大模型命令行问答

一个最小可用的 Python 命令行程序：输入问题，调用大模型 API，先输出一行分隔符 `---`，再以**流式**方式逐字实时打印模型回答。

## 功能

- 单轮问答：不保存上下文，每次都是全新会话
- 流式输出：回答随生成随显示，不等待全部接收完成
- 配置外置：所有连接参数来自 `config.ini`，代码里无硬编码

## 目录结构

```
Practice01/
├── chat.py            # 主程序
├── config.ini         # 配置文件（已被 .gitignore 忽略）
├── requirements.txt   # 依赖
├── .gitignore
└── README.md
```

## 环境要求

- Python 3.8+
- 一个兼容 OpenAI 接口格式的 API 地址与密钥

## 安装与运行

```bash
pip install -r requirements.txt
python chat.py
```

在 Windows 终端若中文显示乱码，先执行：

```bash
chcp 65001
```

或在运行前设置 `PYTHONIOENCODING=utf-8`。

## 配置说明

编辑 `config.ini`，配置段固定为 `[llm]`，仅以下三个参数：

```ini
[llm]
base_url=https://api.deepseek.com/v1
model_name=deepseek-chat
api_key=your-api-key-here
```

| 参数 | 说明 |
| --- | --- |
| `base_url` | API 地址，需兼容 OpenAI 接口格式 |
| `model_name` | 模型名称 |
| `api_key` | API 密钥 |

示例中以 DeepSeek 为例，替换成任意兼容 OpenAI 协议的服务即可（如通义千问、Kimi、Ollama 本地模型等）。

## 代码说明

核心流程只有几步：

1. `configparser` 读取同目录下的 `config.ini`
2. 用读取到的参数构造 `OpenAI` 客户端
3. `input()` 获取问题
4. 打印 `---`
5. 以 `stream=True` 调用接口，遍历每个数据块，打印 `delta.content`，末尾补一个换行

```python
for chunk in client.chat.completions.create(
    model=llm["model_name"],
    messages=[{"role": "user", "content": question}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

`end=""` 取消自动换行，`flush=True` 保证每收到一块就立刻显示。

## 安全提示

`config.ini` 已写入 `.gitignore`，密钥不会被提交到 GitHub。切勿把真实密钥硬编码进 `chat.py` 或提交到版本库；若密钥曾经泄露，请立即在服务商控制台重置。
