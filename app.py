from pathlib import Path
from time import perf_counter

import streamlit as st
from dotenv import load_dotenv

from conversation import Conversation, Turn
from grounding import AnswerResult
from rag_core import answer_document, retrieve_document
from model_services import ModelSession, load_services
from send_preview import PreviewFlow, PreviewRequired

ROOT = Path(__file__).parent
load_dotenv()
st.set_page_config(page_title="知页 · 文档问答", page_icon="📚", layout="wide")
st.markdown("<style>" + (ROOT / "assets/style.css").read_text() + "</style>", unsafe_allow_html=True)
st.markdown('<div class="eyebrow">知页 / DOCUMENT ASSISTANT</div>', unsafe_allow_html=True)
st.title("让每个回答，都有出处。")
st.caption("试用版 · 2026-10-18｜请使用公开或有权处理的文档，重要答案需回看原文。")
st.markdown('<div class="intro">读懂文档，接着追问。把结论和原文放在一起核对。</div>', unsafe_allow_html=True)

if "conversation" not in st.session_state:
    st.session_state.conversation = Conversation()
conversation = st.session_state.conversation
if "model_session" not in st.session_state:
    st.session_state.model_session = ModelSession()
model_session = st.session_state.model_session
try:
    services = load_services()
except ValueError as exc:
    services = []
    st.error(str(exc))
service = None


def clear_index():
    retriever = st.session_state.pop("vector_retriever", None)
    if retriever is not None:
        retriever.clear()


def clear_conversation():
    st.session_state.pop("preview_flow", None)
    conversation.turns.clear()
    st.session_state.clear_confirm = False


@st.cache_resource
def load_embedding_model():
    from vector_retrieval import LocalEmbedder
    return LocalEmbedder()


with st.sidebar:
    st.subheader("数据与模型服务")
    st.caption("上传文件先到运行本应用的服务器。解析、关键词检索和向量化在该服务器执行；首次语义检索需下载模型。")
    if services:
        service_id = st.selectbox("回答服务", [s.id for s in services],
            format_func=lambda value: next(s.name for s in services if s.id == value))
        service = next(s for s in services if s.id == service_id)
        if st.session_state.get("selected_service_fingerprint") != service.fingerprint:
            model_session.revoke()
            st.session_state.selected_service_fingerprint = service.fingerprint
        st.text(f"接收方：{service.provider}\n模型：{service.model}\n地址：{service.base_url}")
    st.caption("发送内容：问题、检索到的原文（含文件名与位置）；仅在允许历史问答时，追问改写会发送最近三轮有效问题和回答。短文档可能全部进入候选原文。")
    st.caption("服务品牌不代表数据安全承诺。请依据企业批准的部署方式和数据规则使用；切换服务不会自动清除历史回答。")
    st.divider()
    st.subheader("资料库")
    use_demo = st.toggle("使用内置示例", help="虚构员工手册，可体验直接提问、追问和资料不足提示。")
    uploaded = st.file_uploader("选择文档", type=["pdf", "docx", "txt"], disabled=use_demo,
                                help="支持文字版 PDF、Word 和 UTF-8 TXT，最大 20 MB。")
    mode = st.radio("检索方式", ["关键词检索", "语义检索"],
                    help="关键词适合原文中的具体词语；语义检索更适合换一种说法的问题。")
    if mode == "语义检索":
        st.caption("首次启用需要加载中文模型，可能比后续提问更慢。")
    st.divider()
    st.caption("问答与调用元数据仅保存在当前会话。调用记录不含文档正文、问题、回答或密钥，刷新可能丢失。")
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
            model_session.revoke()
        clear_index()
        pending = False
elif pending:
    with st.spinner("正在读取文档…"):
        conversation.select_document(data, filename)
        model_session.revoke()
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

blocked = False
include_history = True
if conversation.document:
    with st.sidebar:
        st.subheader("当前文档发送规则")
        blocked = st.toggle("禁止发送给模型服务", key="blocked_" + conversation.document_key,
                            value=conversation.document_key in model_session.blocked_documents,
                            help="仍可在应用服务器上解析和关键词检索；不会调用回答或追问模型。")
        if blocked != (conversation.document_key in model_session.blocked_documents):
            model_session.set_document_blocked(conversation.document_key, blocked)
        include_history = st.checkbox("允许发送历史问答以理解追问", value=True,
                                      key="include_history", disabled=blocked)
        model_session.set_history_allowed(include_history)
        if not include_history:
            st.caption("只发送本轮完整问题与候选原文。请写明主题；历史记录仍保留在页面中。")

if blocked:
    st.info("当前文档禁止模型调用。文件仍由应用服务器处理；下方可检索原文，不生成 AI 回答。此处只做关键词检索，不触发向量模型下载。禁止发送无法撤回此前已发送的内容。")

if conversation.document and not pending and not too_large and conversation.document.passages:
    with st.expander("仅检索原文 · 不调用模型", expanded=blocked):
        with st.form("original_passages"):
            local_query = st.text_input("输入文档中的关键词", max_chars=400)
            local_submit = st.form_submit_button("查找原文")
        if local_submit and local_query.strip():
            local_sources = retrieve_document(conversation.document, local_query)
            if not local_sources:
                st.info("未找到匹配原文，请换用文档中的词语。")
            for source in local_sources:
                with st.container(border=True):
                    st.text(source.label)
                    st.write(source.text)
            st.caption("结果按关键词匹配排序，不表示这些片段足以回答问题。")

with st.sidebar:
    st.subheader("回答与发送选项")
    expand_evidence = st.checkbox("补充长文证据（最多 6 处）", value=True,
        help="原模式取前三片段；补充模式最多六处，会增加发送文字量，仍不保证覆盖全部证据。")
    review_conditions = st.checkbox("回答后核对关键条件", value=False,
        help="已回答问题增加一次同服务模型核对，增加费用和耗时；核对模型仍可能漏判或误报。")
    preview_enabled = st.checkbox("每次发送前查看内容", value=False,
        help="在追问改写、回答生成、条件核对前分别查看完整发送文本。取消后无法撤回已完成的请求。")
    if review_conditions:
        st.caption("核对会发送本轮候选原文、问题与生成的回答；发现问题时先显示原文，不自动修补答案。")

configured = bool(service and service.configured)
approved = bool(service and model_session.allowed(service, conversation.document_key))
if configured and conversation.document and not pending and not too_large and not blocked:
    if not approved:
        st.warning("请确认这份文档可以发给上方所列模型服务。更换文档、服务地址或模型后需要重新确认。当前历史发送设置会一并生效，请检查侧栏。")
        if st.button("确认接收方并允许当前文档问答", type="primary"):
            model_session.approve(service, conversation.document_key)
            st.rerun()
    elif st.button("撤回发送许可"):
        model_session.revoke()
        st.rerun()
if not configured:
    st.warning("尚未配置回答服务。可以先查看文档；已有问答仍可导出。")

scope = (conversation.document_key, service.fingerprint if service else None,
         include_history, mode, review_conditions, expand_evidence,
         tuple((t.question, t.result.answer, t.result.status) for t in conversation.turns))
flow = st.session_state.get("preview_flow")
if flow and (flow.scope != scope or blocked or not approved or not configured or pending or too_large or not preview_enabled):
    st.session_state.pop("preview_flow", None)
    flow = None
    st.info("发送范围或设置已变化，待发送请求已取消；已完成的请求无法撤回。")
resume = False
if flow and flow.pending:
    labels = {"rewrite": "理解追问", "answer": "生成回答", "review": "核对条件"}
    with st.container(border=True):
        st.subheader("本次发送预览 · " + labels.get(flow.pending["phase"], "模型调用"))
        st.text(f"接收方：{service.provider} · 模型：{service.model}")
        st.caption("以下是本次实际发送的完整文本，含任务说明与资料。不会发送密钥到正文。短资料可能全部包含在内。")
        st.text(flow.pending["prompt"])
        c1, c2 = st.columns(2)
        if c1.button("确认发送本次内容", type="primary"):
            flow.approve()
            resume = True
        if c2.button("取消本轮问答"):
            st.session_state.pop("preview_flow", None)
            st.rerun()

question = st.chat_input("问一个问题，也可以接着上一轮追问…", max_chars=400,
                         disabled=bool(flow or pending or too_large or blocked or not configured or not approved or not conversation.document or not conversation.document.passages))
if question or resume:
    question = flow.question if resume else question.strip()
    if preview_enabled and not flow:
        flow = PreviewFlow(question, scope, len(model_session.records))
        st.session_state.preview_flow = flow
    start = perf_counter()
    record_start = flow.record_start if flow else len(model_session.records)
    paused = False
    if flow:
        flow.begin()
    with st.status("正在处理问题…", expanded=True) as progress:
        try:
            retriever = None
            if mode == "语义检索":
                from vector_retrieval import VectorRetriever
                if "vector_retriever" not in st.session_state:
                    st.write("正在加载语义检索模型…")
                    st.session_state.vector_retriever = VectorRetriever(load_embedding_model())
                retriever = st.session_state.vector_retriever
            sender = lambda prompt, phase, chunks: model_session.call(service, conversation.document_key, prompt, phase, chunks)
            caller = (lambda prompt, phase, chunks: flow.call(prompt, phase, chunks, sender)) if flow else sender
            result = answer_document(conversation.document, question, retriever,
                                     history=conversation.turns if include_history else (), on_progress=st.write,
                                     model_call=caller, source_limit=6 if expand_evidence else 3,
                                     review_conditions=review_conditions)
        except PreviewRequired:
            paused = True
        except Exception as exc:
            result = AnswerResult(str(exc), "error", reason_code="service_or_processing_error",
                                  next_step="根据错误提示检查服务或稍后重试；不会自动切换模型。")
        if paused:
            progress.update(label="等待确认发送", state="complete", expanded=False)
        else:
            progress.update(label="处理完成" if result.status not in {"error", "unverified"} else "本轮需要检查",
                            state="complete" if result.status not in {"error", "unverified"} else "error", expanded=False)
    if flow:
        flow.active_seconds += perf_counter() - start
    if paused:
        st.rerun()
    conversation.turns.append(Turn(question, result, mode, flow.active_seconds if flow else perf_counter() - start,
        service.name, service.model, tuple(r["call_id"] for r in model_session.records[record_start:]), include_history))
    st.session_state.pop("preview_flow", None)
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
        if result.next_step:
            st.caption("下一步：" + result.next_step)
        if result.review_status == "passed":
            st.caption("条件模型核对通过；这是模型判断，仍请结合原文确认。")
        if result.review_notes:
            with st.expander("条件核对发现"):
                for note in result.review_notes:
                    st.text(note)
        if result.retrieval_query and result.retrieval_query != turn.question:
            st.caption("本轮理解的问题：" + result.retrieval_query)
        duration = f" · {turn.elapsed_seconds:.1f} 秒" if turn.elapsed_seconds is not None else ""
        st.caption(f"第 {number} 轮 · {turn.mode}{duration}")
        if turn.service_name:
            st.caption(f"服务：{turn.service_name} · 模型：{turn.model} · 历史问答：{'允许发送' if turn.history_allowed else '不发送'}")
            with st.expander("本轮调用编号"):
                st.text("\n".join(turn.call_ids) or "本轮未调用模型")
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

if model_session.records:
    with st.sidebar:
        with st.expander("调用追溯"):
            st.caption("这些记录用于定位调用，不能证明服务商泄漏数据，也不是不可篡改的审计凭证。问答导出另含正文，请谨慎分享。")
            st.dataframe([{k: r[k] for k in ("time_utc", "service_id", "model", "phase", "status")} for r in model_session.records])
            st.download_button("导出调用元数据", model_session.export(), file_name="调用元数据.json", mime="application/json")
            if st.button("清空调用元数据"):
                model_session.records.clear()
                st.rerun()
