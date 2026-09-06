import os
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    api_key="FI6uniS0LSOPCl40vjPwQumX4pMeiX8V",  # 把这里替换成你的 SecretKey
    base_url="https://api.hunyuan.cloud.tencent.com/v1"
)

# 发送第一条消息
response = client.chat.completions.create(
    model="hunyuan-lite",  # 混元免费模型
    messages=[
        {"role": "system", "content": "你是一个有用的AI助手。"},
        {"role": "user", "content": "用一句话解释什么是RAG技术。"}
    ]
)
print(response.choices[0].message.content)