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


@dataclass
class Conversation:
    document_key: str | None = None
    document: object = None
    error: str = ""
    turns: list[Turn] = field(default_factory=list)

    def select_document(self, data, filename=""):
        key = hashlib.sha256(filename.encode() + b"\0" + data).hexdigest() if data is not None else None
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
            if turn.result.retrieval_query != turn.question and turn.result.retrieval_query:
                lines.extend([f"本轮理解的问题：{turn.result.retrieval_query}", ""])
            for i, source in enumerate(turn.result.sources, 1):
                lines.extend([f"### 来源{i}：{source.label}", "", source.text, ""])
        return "\n".join(lines)
