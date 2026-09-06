# app.py - 使用 RAG 的 Streamlit 应用

import streamlit as st
import os
from dotenv import load_dotenv
from pypdf import PdfReader
import docx
import tempfile
from rag_core import rag_query

# 配置
load_dotenv()

st.set_page_config(
    page_title="📚 RAG知识库助手",
    page_icon="📚",
    layout="wide"
)

API_KEY = os.getenv("TENCENT_API_KEY")
if not API_KEY:
    st.error("❌ 错误：TENCENT_API_KEY 没有设置")
    st.stop()

# 文档加载函数
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
        return None

# UI 布局
st.title("📚 AI知识库问答系统（基于RAG）")
st.markdown("上传文档，使用RAG技术智能问答")

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
        placeholder="例如：这个文档的主要内容是什么？"
    )

# 提问逻辑
if st.button("🚀 提问", use_container_width=True):
    if uploaded_file is None:
        st.error("⚠️ 请先上传文档")
    elif not question.strip():
        st.error("⚠️ 请输入问题")
    else:
        # 读取文档
        with st.spinner("📖 读取文档中..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name
            
            content = load_document(tmp_path)
            os.remove(tmp_path)
        
        if content is None:
            st.error("❌ 文档读取失败")
        elif len(content.strip()) < 100:
            st.warning("⚠️ 文档内容太短，无法处理")
        else:
            # 使用 RAG 查询
            with st.spinner("🤖 RAG 分析中..."):
                try:
                    answer, sources = rag_query(content, question)
                    
                    # 显示结果
                    st.success("✅ 回答完成")
                    
                    st.subheader("💡 回答")
                    st.write(answer)
                    
                    # 显示相关段落
                    with st.expander("📖 相关段落（来源）"):
                        for i, source in enumerate(sources, 1):
                            st.markdown(f"**段落 {i}:**")
                            st.write(source)
                            st.divider()
                    
                    # 文档信息
                    with st.expander("📊 文档统计"):
                        st.write(f"**文件名**: {uploaded_file.name}")
                        st.write(f"**文档长度**: {len(content):,} 字符")
                        st.write(f"**问题**: {question}")
                
                except Exception as e:
                    st.error(f"❌ 错误: {str(e)}")