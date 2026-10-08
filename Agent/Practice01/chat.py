import configparser

from openai import OpenAI

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")
llm = config["llm"]

client = OpenAI(base_url=llm["base_url"], api_key=llm["api_key"])

messages = []

while True:
    try:
        question = input("请输入问题: ").strip()

        messages.append({"role": "user", "content": question})

        print("---")

        reply = ""
        for chunk in client.chat.completions.create(
            model=llm["model_name"],
            messages=messages,
            stream=True,
        ):
            delta = chunk.choices[0].delta.content or ""
            reply += delta
            print(delta, end="", flush=True)

        messages.append({"role": "assistant", "content": reply})

        print()
    except KeyboardInterrupt:
        print("\n已停止")
        break
