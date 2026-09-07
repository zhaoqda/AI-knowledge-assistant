from pathlib import Path
from time import perf_counter
import os

import streamlit as st
from dotenv import load_dotenv

from conversation import Conversation, Turn
from grounding import AnswerResult
from rag_core import answer_document

ROOT = Path(__file__).parent
load_dotenv()
st.set_page_config(page_title="知页 · 文档问答", page_icon="📚", layout="wide")
st.markdown("<style>" + (ROOT / "assets/style.css").read_text() + "</style>", unsafe_allow_html=True)
st.markdown('<div class="eyebrow">知页 / DOCUMENT ASSISTANT</div>', unsafe_allow_html=True)
st.title("让每个回答，都有出处。")
st.markdown('<div class="intro">读懂文档，接着追问。把结论和原文放在一起核对。</div>', unsafe_allow_html=True)

if "conversation" not in st.session_state:
    st.session_state.conversation = Conversation()
conversation = st.session_state.conversation


def clear_index():
    retriever = st.session_state.pop("vector_retriever", None)
    if retriever is not None:
        retriever.clear()


def clear_conversation():
    conversation.turns.clear()
    st.session_state.clear_confirm = False


@st.cache_resource
def load_embedding_model():
    from vector_retrieval import LocalEmbedder
    return LocalEmbedder()


with st.sidebar:
    st.subheader("资料库")
    use_demo = st.toggle("使用内置示例", help="虚构员工手册，可体验直接提问、追问和资料不足提示。")
    uploaded = st.file_uploader("选择文档", type=["pdf", "docx", "txt"], disabled=use_demo,
                                help="支持文字版 PDF、Word 和 UTF-8 TXT，最大 20 MB。")
    mode = st.radio("检索方式", ["关键词检索", "语义检索"],
                    help="关键词适合原文中的具体词语；语义检索更适合换一种说法的问题。")
    if mode == "语义检索":
        st.caption("首次启用需要加载中文模型，可能比后续提问更慢。")
    st.divider()
    st.caption("回答会使用在线模型处理问题及选中的原文。记录保存在当前会话，可随时导出。")
    with st.expander("会话管理"):
        clear_requested = st.checkbox("确认清空当前问答", key="clear_confirm", disabled=not conversation.turns)
        st.button("清空对话", disabled=not (clear_requested and conversation.turns), on_click=clear_conversation)
        if st.button("清除索引（保留对话）"):
            clear_index()
        st.caption("刷新或关闭页面可能丢失记录。清空对话后无法在页面中恢复。")

if use_demo:
    data = (ROOT / "examples/员工手册.txt").read_bytes()
    filename = "员工手册（虚构示例）.txt"
else:
    data = uploaded.getvalue() if uploaded else None
    filename = uploaded.name if uploaded else ""

pending = Conversation.key_for(data, filename) != conversation.document_key
too_large = data is not None and len(data) > 20 * 1024 * 1024
if too_large:
    st.error("文件超过 20 MB，请压缩或拆分后再上传。当前记录仍然保留。")
elif pending and conversation.turns:
    st.warning("你选择了新文档或移除了文件。请先导出当前记录，再确认切换；确认前不会清空对话。")
    if st.button("确认切换文档", type="primary"):
        with st.spinner("正在读取文档…"):
            conversation.select_document(data, filename)
        clear_index()
        pending = False
elif pending:
    with st.spinner("正在读取文档…"):
        conversation.select_document(data, filename)
    clear_index()
    pending = False

if conversation.error:
    st.error(conversation.error)
if conversation.document:
    st.text(conversation.document.filename)
    columns = st.columns(3)
    columns[0].metric("已读取文字", f"{len(conversation.document.text):,}")
    columns[1].metric("问答轮次", len(conversation.turns))
    columns[2].metric("最近用时", f"{conversation.turns[-1].elapsed_seconds:.1f} 秒"
                      if conversation.turns and conversation.turns[-1].elapsed_seconds is not None else "—")
    for warning in conversation.document.warnings:
        st.warning(warning)
    if not conversation.document.passages:
        st.warning("未提取到可检索文字。扫描版 PDF 需要先进行 OCR。")
elif not conversation.error:
    with st.container(border=True):
        st.subheader("从一份文档开始")
        st.write("在侧栏上传资料，或开启「使用内置示例」。输入问题后，每轮回答都可以展开原文核对。")
        st.caption("适合员工手册、课程材料和产品说明。扫描图片暂不支持直接识别。")

if conversation.document and not conversation.turns and use_demo:
    st.info("试着问：正式员工年假有几天？ → 那试用期员工呢？ → 公司提供免费午餐吗？")

configured = bool(os.getenv("TENCENT_API_KEY") and os.getenv("TENCENT_API_BASE_URL"))
if not configured:
    st.warning("尚未配置回答服务。可以先查看文档；已有问答仍可导出。")

question = st.chat_input("问一个问题，也可以接着上一轮追问…", max_chars=400,
                         disabled=bool(pending or too_large or not configured or not conversation.document or not conversation.document.passages))
if question and question.strip():
    question = question.strip()
    start = perf_counter()
    with st.status("正在处理问题…", expanded=True) as progress:
        try:
            retriever = None
            if mode == "语义检索":
                from vector_retrieval import VectorRetriever
                if "vector_retriever" not in st.session_state:
                    st.write("正在加载语义检索模型…")
                    st.session_state.vector_retriever = VectorRetriever(load_embedding_model())
                retriever = st.session_state.vector_retriever
            result = answer_document(conversation.document, question, retriever,
                                     history=conversation.turns, on_progress=st.write)
        except Exception as exc:
            result = AnswerResult(str(exc), "error")
        progress.update(label="处理完成" if result.status not in {"error", "unverified"} else "本轮需要检查",
                        state="complete" if result.status not in {"error", "unverified"} else "error", expanded=False)
    conversation.turns.append(Turn(question, result, mode, perf_counter() - start))
    st.rerun()

for number, turn in enumerate(conversation.turns, 1):
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
        duration = f" · {turn.elapsed_seconds:.1f} 秒" if turn.elapsed_seconds is not None else ""
        st.caption(f"第 {number} 轮 · {turn.mode}{duration}")
        if result.sources:
            with st.expander(f"引用原文 · {len(result.sources)} 处"):
                st.caption("编号对应本轮回答。PDF 使用文件页码；请结合原文核对结论。")
                for i, source in enumerate(result.sources, 1):
                    with st.container(border=True):
                        st.markdown(f"**[来源{i}]**")
                        st.text(source.label)
                        st.write(source.text)
        if result.candidates:
            with st.expander("候选原文 · 暂不足以支持回答"):
                for source in result.candidates:
                    with st.container(border=True):
                        st.text(source.label)
                        st.write(source.text)

if conversation.turns:
    with st.sidebar:
        st.download_button("导出问答记录", conversation.export_markdown(),
                           file_name="问答记录.md", mime="text/markdown", use_container_width=True)
