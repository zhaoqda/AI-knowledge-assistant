import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from model_services import ModelService, ModelSession, load_services
from documents import text_document
from rag_core import answer_document


def service(id="a", url="https://example.invalid/v1", model="model-a"):
    return ModelService(id, id, "测试提供方", url, model, "TEST_SERVICE_KEY")


def response(content='{"answerable":false}', status=200):
    result = Mock(status_code=status)
    result.json.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
    return result


class ModelServiceTests(unittest.TestCase):
    def test_unapproved_call_never_sends(self):
        with patch("model_services.requests.post") as post:
            with self.assertRaisesRegex(RuntimeError, "阻止"):
                ModelSession().call(service(), "doc", "secret", "answer")
        post.assert_not_called()

    def test_consent_bound_to_document_endpoint_and_model_and_can_be_revoked(self):
        session = ModelSession()
        a = service()
        session.approve(a, "doc")
        self.assertTrue(session.allowed(a, "doc"))
        self.assertFalse(session.allowed(a, "other"))
        self.assertFalse(session.allowed(service(model="b"), "doc"))
        self.assertFalse(session.allowed(service(url="https://other.invalid/v1"), "doc"))
        session.revoke()
        self.assertFalse(session.allowed(a, "doc"))

    def test_two_services_route_exactly_and_metadata_excludes_content(self):
        session = ModelSession()
        with patch.dict(os.environ, {"TEST_SERVICE_KEY": "secret-key"}), patch("model_services.requests.post", return_value=response()) as post:
            for config in [service(), service("b", "https://b.invalid/v1", "model-b")]:
                session.approve(config, "document-hash")
                session.call(config, "document-hash", "sensitive-document-and-question", "answer", ["chunk-hash"])
                self.assertEqual(post.call_args.args[0], config.base_url + "/chat/completions")
                self.assertEqual(post.call_args.kwargs["json"]["model"], config.model)
                self.assertFalse(post.call_args.kwargs["allow_redirects"])
        serialized = session.export()
        self.assertNotIn("secret-key", serialized)
        self.assertNotIn("sensitive-document-and-question", serialized)
        self.assertEqual(len({r["call_id"] for r in session.records}), 2)
        self.assertEqual(session.records[0]["chunk_ids"], ["chunk-hash"])

    def test_errors_do_not_fallback_or_leak_server_text(self):
        session = ModelSession()
        session.approve(service(), "doc")
        with patch.dict(os.environ, {"TEST_SERVICE_KEY": "test"}), patch("model_services.requests.post", side_effect=RuntimeError("SECRET body")) as post:
            with self.assertRaisesRegex(RuntimeError, "服务调用失败") as error:
                session.call(service(), "doc", "private", "answer")
        self.assertNotIn("SECRET", str(error.exception))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(session.records[0]["status"], "error")

    def test_redirect_is_rejected(self):
        session = ModelSession()
        session.approve(service(), "doc")
        with patch.dict(os.environ, {"TEST_SERVICE_KEY": "test"}), patch("model_services.requests.post", return_value=response(status=302)):
            with self.assertRaisesRegex(RuntimeError, "重定向"):
                session.call(service(), "doc", "private", "answer")

    def test_truncated_and_empty_results_are_service_errors(self):
        session = ModelSession()
        session.approve(service(), "doc")
        for content, reason in [("", "stop"), ("{}", "length")]:
            result = response(content)
            result.json.return_value["choices"][0]["finish_reason"] = reason
            with patch.dict(os.environ, {"TEST_SERVICE_KEY": "test"}), patch("model_services.requests.post", return_value=result):
                with self.assertRaises(RuntimeError):
                    session.call(service(), "doc", "private", "answer")
            self.assertEqual(session.records[-1]["status"], "error")

    def test_http_failures_are_actionable_without_reading_vendor_body(self):
        codes = {302: "redirect_blocked", 401: "authentication_failed",
                 402: "billing_rejected", 403: "access_denied", 429: "request_limited",
                 503: "provider_unavailable", 400: "request_rejected"}
        for status, code in codes.items():
            with self.subTest(status=status):
                session = ModelSession()
                session.approve(service(), "doc")
                result = response(status=status)
                result.text = "SECRET vendor response"
                with patch.dict(os.environ, {"TEST_SERVICE_KEY": "SECRET key"}), patch("model_services.requests.post", return_value=result) as post:
                    with self.assertRaises(RuntimeError) as error:
                        session.call(service(), "doc", "SECRET document", "answer")
                result.json.assert_not_called()
                self.assertEqual(post.call_count, 1)
                self.assertEqual(session.records[0]["error_code"], code)
                self.assertEqual(session.records[0]["http_status"], status)
                self.assertNotIn("SECRET", str(error.exception) + session.export())

    def test_network_failures_are_safe_and_never_automatically_retried(self):
        import requests
        for exception, code, message in [(requests.Timeout("SECRET"), "timeout", "超时"),
                (requests.ConnectionError("SECRET"), "connection_failed", "连接")]:
            with self.subTest(code=code):
                session = ModelSession()
                session.approve(service(), "doc")
                with patch.dict(os.environ, {"TEST_SERVICE_KEY": "test"}), patch("model_services.requests.post", side_effect=exception) as post:
                    with self.assertRaisesRegex(RuntimeError, message) as error:
                        session.call(service(), "doc", "private", "answer")
                self.assertEqual(post.call_count, 1)
                self.assertEqual(session.records[0]["error_code"], code)
                self.assertNotIn("SECRET", str(error.exception) + session.export())

    def test_malformed_response_shape_is_classified(self):
        for payload in [[], {}, {"choices": []}, {"choices": [None]},
                        {"choices": [{"message": None}]}]:
            with self.subTest(payload=payload):
                session = ModelSession()
                session.approve(service(), "doc")
                result = response()
                result.json.return_value = payload
                with patch.dict(os.environ, {"TEST_SERVICE_KEY": "test"}), patch("model_services.requests.post", return_value=result):
                    with self.assertRaisesRegex(RuntimeError, "格式异常"):
                        session.call(service(), "doc", "private", "answer")
                self.assertEqual(session.records[0]["error_code"], "invalid_response")

    def test_invalid_json_then_manual_retry_can_recover(self):
        session = ModelSession()
        session.approve(service(), "doc")
        invalid = response()
        invalid.json.side_effect = ValueError("SECRET server data")
        with patch.dict(os.environ, {"TEST_SERVICE_KEY": "test"}), patch("model_services.requests.post", side_effect=[invalid, response("valid")]) as post:
            with self.assertRaisesRegex(RuntimeError, "格式异常") as error:
                session.call(service(), "doc", "private", "answer")
            self.assertEqual(post.call_count, 1)
            self.assertEqual(session.call(service(), "doc", "private", "answer"), "valid")
        self.assertEqual(session.records[0]["error_code"], "invalid_response")
        self.assertEqual(session.records[1]["status"], "success")
        self.assertNotIn("error_code", session.records[1])
        self.assertNotIn("SECRET", str(error.exception) + session.export())

    def test_unsafe_endpoint_rejected(self):
        for url in ["http://example.com", "https://user:pass@example.com", "https://example.com?token=x", "https://example.com#x"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                service(url=url)

    def test_duplicate_or_invalid_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "services.json"
            path.write_text(json.dumps([service().__dict__, service().__dict__]))
            with patch.dict(os.environ, {"MODEL_SERVICES_CONFIG": str(path)}), self.assertRaises(ValueError):
                load_services()

    def test_no_match_sends_nothing_and_followup_has_separate_phases(self):
        from conversation import Turn
        from grounding import AnswerResult
        session = ModelSession()
        session.approve(service(), "doc")
        caller = lambda prompt, phase, chunks: session.call(service(), "doc", prompt, phase, chunks)
        doc = text_document("正式员工每年有十天年假。")
        with patch.dict(os.environ, {"TEST_SERVICE_KEY": "test"}), patch("model_services.requests.post", side_effect=[response('{"question":"员工年假几天？"}'), response()]) as post:
            self.assertEqual(answer_document(doc, "午餐免费吗？", model_call=caller).status, "no_match")
            post.assert_not_called()
            history = [Turn("年假？", AnswerResult("十天", "answered"), "关键词")]
            answer_document(doc, "那几天？", history=history, model_call=caller)
        self.assertEqual([r["phase"] for r in session.records], ["rewrite", "answer"])
        self.assertEqual(session.records[0]["chunk_ids"], [])
        self.assertTrue(session.records[1]["chunk_ids"])

    def test_missing_credential_prevents_sending(self):
        session = ModelSession()
        session.approve(service(), "doc")
        with patch.dict(os.environ, {"TEST_SERVICE_KEY": ""}), patch("model_services.requests.post") as post:
            with self.assertRaisesRegex(RuntimeError, "密钥"):
                session.call(service(), "doc", "private", "answer")
        post.assert_not_called()

    def test_interface_service_switch_revokes_consent_preserves_provenance(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "services.json"
            path.write_text(json.dumps([service().__dict__, service("b", "https://b.invalid/v1", "model-b").__dict__]))
            with patch.dict(os.environ, {"MODEL_SERVICES_CONFIG": str(path), "TEST_SERVICE_KEY": "test"}), patch("model_services.requests.post", return_value=response()) as post:
                app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30).run()
                app.toggle[0].set_value(True).run()
                next(b for b in app.button if b.label == "确认接收方并允许当前文档问答").click().run()
                app.chat_input[0].set_value("正式员工年假几天？").run()
                app.selectbox[0].set_value("b").run()
                self.assertTrue(app.chat_input[0].disabled)
                self.assertEqual(post.call_count, 1)
                self.assertEqual(app.session_state.conversation.turns[0].model, "model-a")
                self.assertIn("模型：model-a", app.session_state.conversation.export_markdown())
                app.selectbox[0].set_value("a").run()
                self.assertTrue(app.chat_input[0].disabled)
                self.assertFalse(app.exception)

    def test_interface_requires_confirmation_and_records_chosen_service(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ, {"TENCENT_API_KEY": "test", "TENCENT_API_BASE_URL": "https://example.invalid/v1", "MODEL_SERVICES_CONFIG": ""}), patch("model_services.requests.post", return_value=response()) as post:
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30).run()
            app.toggle[0].set_value(True).run()
            self.assertTrue(app.chat_input[0].disabled)
            post.assert_not_called()
            next(b for b in app.button if b.label == "确认接收方并允许当前文档问答").click().run()
            app.chat_input[0].set_value("正式员工年假几天？").run()
            self.assertFalse(app.exception)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(app.session_state.conversation.turns[0].model, "hy3")
            self.assertEqual(len(app.session_state.model_session.records), 1)
            next(b for b in app.button if b.label == "撤回发送许可").click().run()
            self.assertTrue(app.chat_input[0].disabled)


if __name__ == "__main__":
    unittest.main()
