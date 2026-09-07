import os

import streamlit as st
from dotenv import load_dotenv

from conversation import Conversation, Turn
from grounding import AnswerResult
from rag_core import answer_document

load_dotenv()
st.set_page_config(page_title="知识库助手", page_icon="📚", layout="wide")
st.title("知识库助手")
st.caption("上传文档，连续提问，并核对每轮回答的原文依据。")

if "conversation" not in st.session_state:
    st.session_state.conversation = Conversation()
conversation = st.session_state.conversation


def clear_index():
    retriever = st.session_state.pop("vector_retriever", None)
    if retriever is not None:
        retriever.clear()


@st.cache_resource
def load_embedding_model():
    from vector_retrieval import LocalEmbedder
    return LocalEmbedder()


with st.sidebar:
    uploaded = st.file_uploader("选择文档", type=["pdf", "docx", "txt"])
    mode = st.radio("检索方式", ["关键词检索", "语义检索"])
    st.caption("语义检索首次使用需下载模型。向量在应用服务器计算，回答仍使用在线模型。")
    st.caption("更换或移除文档会开始新对话，请先导出需要保留的记录。")
    if st.button("清空对话"):
        conversation.turns.clear()
    if st.button("清除索引（保留对话）"):
        clear_index()
    st.caption("记录保存在当前浏览器会话。刷新、关闭页面或服务重启后可能丢失，可下载保存。")

previous_key = conversation.document_key
if conversation.select_document(uploaded.getvalue() if uploaded else None,
                                uploaded.name if uploaded else ""):
    clear_index()
    if previous_key is not None:
        st.info("文档已更换或移除，已开始新的对话。")

if conversation.error:
    st.error(conversation.error)
if conversation.document:
    st.text(f"当前文档：{conversation.document.filename}")
    for warning in conversation.document.warnings:
        st.warning(warning)
    if not conversation.document.passages:
        st.warning("未提取到可检索文字。扫描版 PDF 需要先进行 OCR。")
else:
    st.info("请先上传文档。")

configured = bool(os.getenv("TENCENT_API_KEY") and os.getenv("TENCENT_API_BASE_URL"))
if not configured:
    st.warning("请配置模型服务后再提问；已有记录仍可查看和导出。")

question = st.chat_input("输入问题，也可以接着上一轮追问…", max_chars=400,
                         disabled=not (configured and conversation.document and conversation.document.passages))
if question and question.strip():
    question = question.strip()
    try:
        with st.spinner("理解问题、检索原文并检查回答依据…"):
            retriever = None
            if mode == "语义检索":
                from vector_retrieval import VectorRetriever
                if "vector_retriever" not in st.session_state:
                    st.session_state.vector_retriever = VectorRetriever(load_embedding_model())
                retriever = st.session_state.vector_retriever
            result = answer_document(conversation.document, question, retriever,
                                     history=conversation.turns)
    except Exception as exc:
        result = AnswerResult(str(exc), "error")
    conversation.turns.append(Turn(question, result, mode))

for turn in conversation.turns:
    with st.chat_message("user"):
        st.write(turn.question)
    with st.chat_message("assistant"):
        result = turn.result
        if result.status == "answered":
            st.write(result.answer)
        elif result.status in {"error", "unverified"}:
            st.error(result.answer)
        else:
            st.info(result.answer)
        if result.retrieval_query and result.retrieval_query != turn.question:
            st.caption("本轮理解的问题：" + result.retrieval_query)
        st.caption("本轮检索方式：" + turn.mode)
        if result.sources:
            with st.expander("引用原文"):
                st.caption("来源编号仅对应本轮回答。PDF 使用文件物理页码；引用存在不等于结论已被完全核验。")
                for i, source in enumerate(result.sources, 1):
                    st.markdown(f"**[来源{i}]**")
                    st.text(source.label)
                    st.write(source.text)
        if result.candidates:
            with st.expander("检索候选（未作为答案依据）"):
                for source in result.candidates:
                    st.text(source.label)
                    st.write(source.text)

if conversation.turns:
    with st.sidebar:
        st.download_button("导出问答记录", conversation.export_markdown(),
                           file_name="问答记录.md", mime="text/markdown")
