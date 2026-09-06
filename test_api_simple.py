# -*- coding: utf-8 -*-
import requests
import json
import time

API_KEY = "sk-6EkfDwJ4MwvlPcIxUvjJXWkmeFCLWQB6P44fZyikme7ovthw"
BASE_URL = "https://tokenhub.tencentmaas.com/v1"

def test_api():
    print("🚀 开始测试 API...")
    
    try:
        start_time = time.time()
        
        # 最简单的请求
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "hy3",
                "messages": [
                    {"role": "system", "content": "你是一个严谨的文档问答助手。"},
                    {"role": "user", "content": "请用一句话介绍什么是RAG技术。"}
                ],
                "temperature": 0.3
            },
            timeout=30
        )
        
        elapsed = time.time() - start_time
        print(f"⏱️ 耗时: {elapsed:.2f} 秒")
        print(f"📊 HTTP 状态码: {response.status_code}")
        
        # 检查响应
        response.raise_for_status()
        result = response.json()
        
        print("\n✅ 成功！API 返回内容：")
        print("=" * 50)
        print(result['choices'][0]['message']['content'])
        print("=" * 50)
        print(f"\n📈 Token 消耗: {result.get('usage', {}).get('total_tokens', 0)}")
        
    except requests.exceptions.Timeout:
        print("❌ 请求超时 (30秒)")
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"响应内容: {e.response.text}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")

if __name__ == "__main__":
    test_api()