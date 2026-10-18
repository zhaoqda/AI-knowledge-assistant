"""Keep a document and its turns together for one browser session."""

from dataclasses import dataclass, field
import hashlib

from documents import read_document
from grounding import AnswerResult


@dataclass(frozen=True)
class Turn:
    question: str
    result: AnswerResult
    mode: str
    elapsed_seconds: float | None = None
    service_name: str = ""
    model: str = ""
    call_ids: tuple[str, ...] = ()
    history_allowed: bool = True


@dataclass
class Conversation:
    document_key: str | None = None
    document: object = None
    error: str = ""
    turns: list[Turn] = field(default_factory=list)

    @staticmethod
    def key_for(data, filename=""):
        return hashlib.sha256(filename.encode() + b"\0" + data).hexdigest() if data is not None else None

    def select_document(self, data, filename=""):
        key = self.key_for(data, filename)
        if key == self.document_key:
            return False
        self.document_key = key
        self.document = None
        self.error = ""
        self.turns.clear()
        if data is not None:
            try:
                self.document = read_document(data, filename)
            except ValueError as exc:
                self.error = str(exc)
        return True

    def export_markdown(self):
        lines = ["# 文档问答记录", "", self.document.filename if self.document else "", ""]
        for number, turn in enumerate(self.turns, 1):
            lines.extend([f"## 第 {number} 轮", "", f"问题：{turn.question}", "",
                          f"检索方式：{turn.mode}；状态：{turn.result.status}", "",
                          turn.result.answer, ""])
            if turn.result.reason_code:
                lines.extend([f"原因分类：{turn.result.reason_code}", f"下一步：{turn.result.next_step}", ""])
            if turn.result.review_status != "not_requested":
                lines.extend([f"条件模型核对：{turn.result.review_status}（不代表语义保证）", ""])
                lines.extend(turn.result.review_notes)
            if turn.service_name:
                lines.extend([f"模型服务：{turn.service_name}；模型：{turn.model}",
                              f"历史问答发送：{'允许' if turn.history_allowed else '关闭'}",
                              f"调用编号：{', '.join(turn.call_ids) or '本轮未调用模型'}", ""])
            if turn.elapsed_seconds is not None:
                lines.extend([f"本轮用时：{turn.elapsed_seconds:.1f} 秒", ""])
            if turn.result.retrieval_query != turn.question and turn.result.retrieval_query:
                lines.extend([f"本轮理解的问题：{turn.result.retrieval_query}", ""])
            for i, source in enumerate(turn.result.sources, 1):
                lines.extend([f"### 来源{i}：{source.label}", "", source.text, ""])
        return "\n".join(lines)
