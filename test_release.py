import unittest
from unittest.mock import patch
from pathlib import Path
from streamlit.testing.v1 import AppTest

from documents import text_document
from grounding import AnswerResult
from evaluation.run import evaluate, score_answer


class ReleaseTests(unittest.TestCase):
    def test_empty_or_truncated_service_response_is_error(self):
        import rag_core
        for content, reason, message in [("", "stop", "有效正文"), ("{}", "length", "截断")]:
            with self.subTest(reason=reason), patch.object(rag_core, "API_KEY", "test"), patch.object(rag_core, "BASE_URL", "https://example.invalid"), patch.object(rag_core.requests, "post") as post:
                post.return_value.json.return_value = {"choices": [{"message": {"content": content}, "finish_reason": reason}]}
                with self.assertRaisesRegex(RuntimeError, message):
                    rag_core.call_llm("测试")
                self.assertEqual(post.call_args.kwargs["json"]["thinking"], {"type": "disabled"})

    def test_progress_reports_real_order(self):
        import rag_core
        messages = []
        with patch.object(rag_core, "call_llm", return_value='{"answerable":false}'):
            rag_core.answer_document(text_document("年假十天。"), "年假？", on_progress=messages.append)
        self.assertEqual(messages, ["正在理解问题…", "正在整理文档并检索原文…", "正在根据候选原文生成回答…", "正在检查来源编号和原文摘句…"])

    def test_unverified_is_not_counted_as_successful_refusal(self):
        case = {"answerable": False}
        self.assertFalse(score_answer(AnswerResult("格式错误", "unverified"), case))
        self.assertFalse(score_answer(AnswerResult("服务错误", "error"), case))
        self.assertTrue(score_answer(AnswerResult("资料不足", "insufficient"), case))

    def test_retrieval_only_evaluation_never_calls_model(self):
        with patch("rag_core.call_llm") as model:
            report = evaluate(mode="keyword", answers=False, limit=3)
        model.assert_not_called()
        self.assertEqual(report["case_count"], 3)
        self.assertEqual(report["retrieval"]["answerable_cases"], 2)

    def test_demo_can_load_without_model_credentials(self):
        with patch.dict("os.environ", {"TENCENT_API_KEY": "", "TENCENT_API_BASE_URL": ""}):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            app.toggle[0].set_value(True).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.chat_input[0].disabled)
            self.assertTrue(any("员工手册" in t.value for t in app.text))


if __name__ == "__main__":
    unittest.main()
