"""Deployment-approved model services and session-scoped outbound records.

No document, prompt, answer or credential is stored in audit records.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from urllib.parse import urlsplit
from uuid import uuid4
from time import perf_counter
import requests


class _ResponseError(RuntimeError):
    """Only locally generated, non-sensitive response errors may reach the UI."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _http_error(status):
    if 300 <= status < 400:
        return _ResponseError("模型服务返回重定向，已阻止转发；请联系部署者检查地址。", "redirect_blocked")
    errors = {
        401: ("模型服务密钥无效或已失效，请联系部署者检查密钥。", "authentication_failed"),
        402: ("模型服务拒绝计费请求，请联系部署者检查账户余额与计费状态。", "billing_rejected"),
        403: ("模型服务拒绝访问，请联系部署者检查账号及模型权限。", "access_denied"),
        429: ("模型服务触发请求限制，请稍后重试；若持续出现，请联系部署者检查限额。", "request_limited"),
    }
    if status in errors:
        return _ResponseError(*errors[status])
    if 500 <= status < 600:
        return _ResponseError("模型服务暂时不可用，请稍后重试。", "provider_unavailable")
    if not 200 <= status < 300:
        return _ResponseError("模型服务拒绝请求，请联系部署者检查接口与模型配置。", "request_rejected")
    return None


@dataclass(frozen=True)
class ModelService:
    id: str
    name: str
    provider: str
    base_url: str
    model: str
    key_env: str
    thinking_disabled: bool = False

    def __post_init__(self):
        url = urlsplit(self.base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise ValueError("模型服务地址必须是无账号、查询参数和片段的 HTTPS 地址。")
        if not all(isinstance(x, str) and x.strip() for x in
                   (self.id, self.name, self.provider, self.model, self.key_env)):
            raise ValueError("模型服务配置存在空字段。")

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.__dict__, sort_keys=True).encode()).hexdigest()

    @property
    def configured(self):
        return bool(os.getenv(self.key_env))


def load_services():
    """Only deployment configuration supplies endpoints; never accept them from uploads."""
    path = os.getenv("MODEL_SERVICES_CONFIG")
    inline = os.getenv("MODEL_SERVICES_JSON")
    if path or inline:
        try:
            if inline:
                entries = json.loads(inline)
            else:
                with open(path, encoding="utf-8") as file:
                    entries = json.load(file)
            if not isinstance(entries, list) or not entries:
                raise ValueError()
            services = [ModelService(**entry) for entry in entries]
            if len({s.id for s in services}) != len(services):
                raise ValueError()
            return services
        except Exception:
            raise ValueError("模型服务配置无效，请联系部署者检查配置文件。") from None
    base = os.getenv("TENCENT_API_BASE_URL")
    return [ModelService("tencent", "腾讯 MaaS", "腾讯 MaaS", base,
                         os.getenv("TENCENT_MODEL", "hy3"), "TENCENT_API_KEY", True)] if base else []


@dataclass
class ModelSession:
    consent_scope: tuple | None = None
    records: list = field(default_factory=list)
    blocked_documents: set = field(default_factory=set)
    history_allowed: bool = True

    def set_document_blocked(self, document_id, blocked):
        if blocked:
            self.blocked_documents.add(document_id)
        else:
            self.blocked_documents.discard(document_id)
        self.revoke()

    def set_history_allowed(self, allowed):
        if self.history_allowed != allowed:
            self.history_allowed = allowed
            self.revoke()

    def approve(self, service, document_id):
        if document_id in self.blocked_documents:
            raise RuntimeError("当前文档禁止发送给模型服务。")
        self.consent_scope = (service.fingerprint, document_id, self.history_allowed)

    def allowed(self, service, document_id):
        return (document_id not in self.blocked_documents and
                self.consent_scope == (service.fingerprint, document_id, self.history_allowed))

    def revoke(self):
        self.consent_scope = None

    def call(self, service, document_id, prompt, phase, chunk_ids=()):
        if document_id in self.blocked_documents:
            raise RuntimeError("当前文档禁止发送给模型服务，已阻止调用。")
        if phase == "rewrite" and not self.history_allowed:
            raise RuntimeError("已关闭历史问答发送，已阻止追问改写。")
        if not self.allowed(service, document_id):
            raise RuntimeError("尚未确认本次文档的模型接收方，已阻止发送。")
        if not service.configured:
            raise RuntimeError("所选服务未配置密钥，请联系部署者。")
        record = {"call_id": str(uuid4()), "time_utc": datetime.now(timezone.utc).isoformat(),
                  "service_id": service.id, "provider": service.provider,
                  "model": service.model, "endpoint": service.base_url,
                  "document_id": document_id, "phase": phase,
                  "chunk_ids": list(chunk_ids), "history_text_included": phase == "rewrite",
                  "status": "started"}
        self.records.append(record)
        body = {"model": service.model, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3, "max_tokens": 1500}
        if service.thinking_disabled:
            body["thinking"] = {"type": "disabled"}
        start = perf_counter()
        try:
            response = requests.post(service.base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + os.environ[service.key_env],
                         "Content-Type": "application/json"}, json=body,
                timeout=30, allow_redirects=False)
            record["http_status"] = response.status_code
            error = _http_error(response.status_code)
            if error:
                raise error
            try:
                payload = response.json()
            except ValueError:
                raise _ResponseError("模型服务返回格式异常，请稍后重试或联系部署者。", "invalid_response") from None
            if (not isinstance(payload, dict) or not isinstance(payload.get("choices"), list)
                    or not payload["choices"] or not isinstance(payload["choices"][0], dict)
                    or not isinstance(payload["choices"][0].get("message"), dict)):
                raise _ResponseError("模型服务返回格式异常，请稍后重试或联系部署者。", "invalid_response")
            usage = payload.get("usage")
            if isinstance(usage, dict):
                recorded_usage = {key: usage[key] for key in
                    ("prompt_tokens", "completion_tokens", "total_tokens")
                    if type(usage.get(key)) is int and usage[key] >= 0}
                if recorded_usage:
                    record["usage"] = recorded_usage
            choice = payload["choices"][0]
            content = choice.get("message", {}).get("content")
            if choice.get("finish_reason") == "length":
                raise _ResponseError("模型回答被长度限制截断，请缩小问题范围后重试。", "truncated_response")
            if not isinstance(content, str) or not content.strip():
                raise _ResponseError("模型服务未返回有效正文，请稍后重试。", "empty_response")
            record["status"] = "success"
            return content
        except _ResponseError as exc:
            record["status"] = "error"
            record["error_code"] = exc.code
            raise
        except requests.Timeout:
            record["status"] = "error"
            record["error_code"] = "timeout"
            raise RuntimeError("等待模型服务超时，请稍后重试。此次请求可能已被服务接收，是否计费请查看服务账单。") from None
        except requests.ConnectionError:
            record["status"] = "error"
            record["error_code"] = "connection_failed"
            raise RuntimeError("无法连接模型服务，请检查网络或稍后重试。") from None
        except Exception:
            record["status"] = "error"
            record["error_code"] = "unexpected_error"
            raise RuntimeError("模型服务调用失败，请检查服务配置或稍后重试。") from None

        finally:
            record["elapsed_seconds"] = round(perf_counter() - start, 3)

    def export(self):
        return json.dumps(self.records, ensure_ascii=False, indent=2)
