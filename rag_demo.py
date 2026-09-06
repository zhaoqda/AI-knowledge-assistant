# project1-rag-knowledge-base/app.py

import streamlit as st
import os
from dotenv import load_dotenv
from pypdf import PdfReader
import docx
import requests

# ============ 配置 ============
load_dotenv()

st.set_page_config(
    page_title="📚 RAG知识库助手",
    page_icon="📚",
    layout="wide"
)

API_KEY = os.getenv("TENCENT_API_KEY")
BASE_URL = os.getenv("TENCENT_API_BASE_URL")

if not API_KEY:
    st.error("❌ 错误：TENCENT_API_KEY 没有设置")
    st.stop()

# ============ 文档加载函数 ============
def load_document(file_path):
    """读取PDF/Word/TXT文档"""
    try:
        if file_path.endswith('.pdf'):
            reader = PdfReader(file_path)
            return "".join([page.extract_text() for page in reader.pages])
        elif file_path.endswith('.docx'):
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        return f"读取失败: {str(e)}"

# ============ LLM 调用函数 ============
def call_llm(prompt: str) -> str:
    """调用腾讯MaaS LLM"""
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
                "max_tokens": 300
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ API调用失败: {str(e)}"

# ============ Streamlit UI ============

# 标题和描述
st.title("📚 AI知识库问答系统")
st.markdown("上传文档（PDF/Word/TXT），然后输入问题")

# 两列布局
col1, col2 = st.columns(2)

with col1:
    st.header("📥 上传文档")
    uploaded_file = st.file_uploader(
        "选择文件",
        type=['pdf', 'docx', 'txt'],
        help="支持PDF、Word、TXT格式"
    )

with col2:
    st.header("❓ 提出问题")
    question = st.text_input(
        "输入你的问题",
        placeholder="例如：这个文档讲了什么主要内容？"
    )

# 提问按钮
if st.button("🚀 提问", use_container_width=True):
    if uploaded_file is None:
        st.error("⚠️ 请先上传文档")
    elif not question.strip():
        st.error("⚠️ 请输入问题")
    else:
        # 显示处理状态
        with st.spinner("📖 读取文档中..."):
            # 保存上传的文件到临时位置
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name
            
            # 读取文档
            content = load_document(tmp_path)
            
            # 清理临时文件
            os.remove(tmp_path)
        
        # 检查内容
        if "读取失败" in content or "读取失败" in content:
            st.error(f"❌ {content}")
        elif len(content.strip()) < 10:
            st.warning(f"⚠️ 文档内容太短（仅{len(content)}字符）")
        else:
            # 截断文本（防止超时）
            content_for_prompt = content[:3000]
            
            with st.spinner("🤖 生成回答中..."):
                # 构建提示词
                prompt = f"""根据以下文档内容回答用户的问题。
                
文档内容：
{content_for_prompt}

用户问题：{question}

请直接回答问题。"""
                
                # 调用LLM
                answer = call_llm(prompt)
            
            # 显示结果
            st.success("✅ 回答完成")
            
            with st.expander("📋 回答内容", expanded=True):
                st.write(answer)
            
            with st.expander("📄 文档信息"):
                st.write(f"**文件名**: {uploaded_file.name}")
                st.write(f"**文档长度**: {len(content)} 字符")
                st.write(f"**用于回答的内容**: {len(content_for_prompt)} 字符")