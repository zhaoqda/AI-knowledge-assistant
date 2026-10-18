"""Session-only replay for explicit per-request approval, without repeat sends."""
from dataclasses import dataclass, field
import hashlib
import json


class PreviewRequired(Exception):
    pass


@dataclass
class PreviewFlow:
    question: str
    scope: tuple
    record_start: int
    cache: list = field(default_factory=list)
    pending: dict | None = None
    approved_digest: str | None = None
    cursor: int = 0
    active_seconds: float = 0.0

    def approve(self):
        if self.pending is None:
            raise ValueError('没有待确认的请求。')
        self.approved_digest = self.pending['digest']

    def begin(self):
        self.cursor = 0

    def call(self, prompt, phase, chunks, sender):
        digest = hashlib.sha256(json.dumps([self.scope, phase, list(chunks), prompt],
                              ensure_ascii=False).encode()).hexdigest()
        index = self.cursor
        self.cursor += 1
        if index < len(self.cache):
            old_digest, raw = self.cache[index]
            if old_digest != digest:
                raise RuntimeError('请求内容已变化，请取消后重新提问。')
            return raw
        if self.approved_digest != digest:
            self.pending = {'digest': digest, 'prompt': prompt, 'phase': phase, 'chunk_ids': list(chunks)}
            raise PreviewRequired()
        self.approved_digest = None
        self.pending = None
        raw = sender(prompt, phase, chunks)
        self.cache.append((digest, raw))
        return raw
