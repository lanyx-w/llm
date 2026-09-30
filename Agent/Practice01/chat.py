import configparser

from openai import OpenAI

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")
llm = config["llm"]

client = OpenAI(base_url=llm["base_url"], api_key=llm["api_key"])

question = input("请输入问题: ").strip()

print("---")

for chunk in client.chat.completions.create(
    model=llm["model_name"],
    messages=[{"role": "user", "content": question}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)

print()
