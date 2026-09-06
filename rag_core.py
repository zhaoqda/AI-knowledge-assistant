# rag_core.py

import os
from dotenv import load_dotenv
import requests
from typing import List, Tuple

load_dotenv()

API_KEY = os.getenv("TENCENT_API_KEY")
BASE_URL = os.getenv("TENCENT_API_BASE_URL")

if not API_KEY:
    raise ValueError("TENCENT_API_KEY not set")

def chunk_text(text: str, chunk_size: int = 500) -> List[str]:
    """把文本分成小块"""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i+chunk_size])
    return chunks

def simple_retrieve(chunks: List[str], query: str, k: int = 3) -> List[Tuple[str, float]]:
    """简单的关键词检索"""
    query_words = set(query.split())
    scores = []
    for chunk in chunks:
        chunk_words = set(chunk.split())
        overlap = len(query_words & chunk_words)
        scores.append((chunk, overlap))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:k]

def call_llm(prompt: str) -> str:
    """调用腾讯 MaaS LLM"""
    try:
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "hy3",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ API 调用失败: {str(e)}"

def rag_query(text: str, query: str) -> Tuple[str, List[str]]:
    """完整的 RAG 查询"""
    # 分块
    chunks = chunk_text(text, chunk_size=500)
    print(f"📖 分块完成: {len(chunks)} 块")
    
    # 检索相关段落
    retrieved = simple_retrieve(chunks, query, k=3)
    print(f"🔍 检索完成: 找到 {len(retrieved)} 个相关段落")
    
    # 构建提示词
    context = "\n\n---\n\n".join([
        f"【相关段落 {i+1}】\n{chunk}"
        for i, (chunk, _) in enumerate(retrieved)
    ])
    
    prompt = f"""根据以下文档段落回答用户问题。

【文档内容】
{context}

【用户问题】
{query}

请直接回答问题。"""
    
    # 调用 LLM
    answer = call_llm(prompt)
    
    # 提取来源
    sources = [chunk for chunk, _ in retrieved]
    
    return answer, sources