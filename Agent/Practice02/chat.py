import configparser
import locale
import os
import subprocess

from openai import OpenAI

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")
llm = config["llm"]

client = OpenAI(base_url=llm["base_url"], api_key=llm["api_key"])

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间（调用本地 date 命令，而不是用 Python 计算）",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }
]


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True)
    data = result.stdout
    if result.returncode != 0 and not data:
        data = result.stderr

    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        try:
            return data.decode(encoding).strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace").strip()


def get_date():
    if os.name == "nt":
        date_text = run_command(["cmd", "/c", "date", "/t"])
        time_text = run_command(["cmd", "/c", "time", "/t"])
        return " ".join(part for part in (date_text, time_text) if part)
    return run_command(["date", "+%Y-%m-%d %H:%M:%S"])


def call_tool(name):
    if name == "getDate":
        return get_date()
    return "未知工具: " + name


def stream_reply(messages):
    reply = ""
    tool_calls = []

    for chunk in client.chat.completions.create(
        model=llm["model_name"],
        messages=messages,
        tools=TOOLS,
        stream=True,
    ):
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        if delta.content:
            reply += delta.content
            print(delta.content, end="", flush=True)

        for tool_delta in delta.tool_calls or []:
            while len(tool_calls) <= tool_delta.index:
                tool_calls.append(
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                )
            slot = tool_calls[tool_delta.index]
            if tool_delta.id:
                slot["id"] = tool_delta.id
            slot["function"]["name"] += tool_delta.function.name or ""
            slot["function"]["arguments"] += tool_delta.function.arguments or ""

    if reply:
        print()
    return reply, tool_calls


messages = []

while True:
    try:
        question = input("请输入问题: ").strip()
        if not question:
            continue

        messages.append({"role": "user", "content": question})

        print("---")

        while True:
            reply, tool_calls = stream_reply(messages)

            if not tool_calls:
                messages.append({"role": "assistant", "content": reply})
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": reply or None,
                    "tool_calls": tool_calls,
                }
            )

            for tool_call in tool_calls:
                name = tool_call["function"]["name"]
                print(f"[调用工具] {name}")
                output = call_tool(name)
                print(f"[工具返回] {output}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": output,
                    }
                )
    except (KeyboardInterrupt, EOFError):
        print("\n已停止")
        break
