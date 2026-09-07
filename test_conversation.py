import json
import unittest
from unittest.mock import Mock, patch

from conversation import Conversation, Turn
from documents import SourceChunk, text_document
from grounding import AnswerResult, validate_answer


def reply(text="十天", source_id=1, quote="正式员工每年有十天年假。"):
    return json.dumps({"answerable": True, "claims": [
        {"text": text, "source_id": source_id, "quote": quote}]}, ensure_ascii=False)


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.sources = [SourceChunk("正式员工每年有十天年假。", "手册.pdf", (2,))]

    def test_supported_claim_gets_code_generated_citation(self):
        result = validate_answer(reply(), self.sources, "年假多久？")
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.answer, "十天 [来源1]")
        self.assertEqual(result.sources[0].pages, (2,))

    def test_explicit_no_answer_keeps_candidates_separate(self):
        result = validate_answer('{"answerable":false}', self.sources, "午餐免费吗？")
        self.assertEqual(result.status, "insufficient")
        self.assertEqual(result.sources, ())
        self.assertEqual(result.candidates, tuple(self.sources))

    def test_fabricated_quote_rejected(self):
        result = validate_answer(reply(quote="员工享有二十天年假。"), self.sources, "年假多久？")
        self.assertEqual(result.status, "unverified")
        self.assertNotIn("二十天", result.answer)

    def test_invalid_citation_rejected(self):
        for number in [0, 2, True, "1"]:
            self.assertEqual(validate_answer(reply(source_id=number), self.sources, "年假？").status, "unverified")

    def test_malformed_output_is_not_no_answer(self):
        for raw in ['not JSON', '[]', '{"answerable":"false"}', '{"answerable":true,"claims":[]}', '{"answerable":true,"claims":[null]}']:
            self.assertEqual(validate_answer(raw, self.sources, "年假？").status, "unverified")

    def test_trivial_quote_and_embedded_citation_rejected(self):
        self.assertEqual(validate_answer(reply(quote="年假"), self.sources, "年假？").status, "unverified")
        self.assertEqual(validate_answer(reply(text="十天 [来源99]"), self.sources, "年假？").status, "unverified")

    def test_sparse_source_ids_are_remapped(self):
        sources = [SourceChunk("报销需发票。", "资料.txt"), self.sources[0]]
        result = validate_answer(reply(source_id=2), sources, "年假？")
        self.assertEqual(result.answer, "十天 [来源1]")
        self.assertEqual(result.sources, (self.sources[0],))


class ConversationTests(unittest.TestCase):
    def test_same_upload_preserves_history_and_parsing(self):
        conversation = Conversation()
        with patch("conversation.read_document", return_value=text_document("年假十天")) as read:
            conversation.select_document(b"document", "a.txt")
            conversation.turns.append(Turn("年假？", AnswerResult("十天", "answered"), "关键词检索"))
            self.assertFalse(conversation.select_document(b"document", "a.txt"))
        self.assertEqual(len(conversation.turns), 1)
        read.assert_called_once()

    def test_changed_contents_clear_history_even_with_same_name(self):
        conversation = Conversation()
        conversation.select_document(b"old", "same.txt")
        conversation.turns.append(Turn("问题", AnswerResult("旧答案", "answered"), "关键词检索"))
        self.assertTrue(conversation.select_document(b"new", "same.txt"))
        self.assertEqual(conversation.turns, [])
        self.assertEqual(conversation.document.text, "new")

    def test_failed_document_cannot_keep_old_document(self):
        conversation = Conversation()
        conversation.select_document(b"old", "a.txt")
        conversation.select_document(b"\xff", "b.txt")
        self.assertIsNone(conversation.document)
        self.assertTrue(conversation.error)

    def test_removing_document_clears_state(self):
        conversation = Conversation()
        conversation.select_document(b"old", "a.txt")
        self.assertTrue(conversation.select_document(None))
        self.assertIsNone(conversation.document)

    def test_export_contains_questions_answers_and_sources(self):
        conversation = Conversation()
        conversation.select_document("年假十天".encode(), "policy.txt")
        conversation.turns.append(Turn("年假？", AnswerResult("十天 [来源1]", "answered",
            (SourceChunk("年假十天", "policy.txt", locations=("第 1 段",)),), "年假？"), "关键词检索"))
        exported = conversation.export_markdown()
        for value in ["年假？", "十天 [来源1]", "第 1 段", "policy.txt"]:
            self.assertIn(value, exported)


class FollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("dotenv.load_dotenv"):
            import rag_core
        cls.core = rag_core

    def test_followup_rewritten_before_retrieval(self):
        doc = text_document("正式员工每年有十天年假。试用期员工没有年假。")
        previous = Turn("正式员工的年假呢？", AnswerResult("十天", "answered"), "关键词检索")
        retriever = Mock()
        retriever.search.return_value = [(doc.text, 0.8)]
        with patch.object(self.core, "call_llm", side_effect=[
            '{"question":"试用期员工有年假吗？"}',
            reply(text="没有年假", quote="试用期员工没有年假。")]) as model:
            result = self.core.answer_document(doc, "那试用期员工呢？", retriever, [previous])
        self.assertEqual(result.status, "answered")
        self.assertEqual(retriever.search.call_args.args[1], "试用期员工有年假吗？")
        self.assertEqual(result.retrieval_query, "试用期员工有年假吗？")
        self.assertNotIn('"answer": "十天"', model.call_args_list[1].args[0])

    def test_first_question_skips_rewriting(self):
        with patch.object(self.core, "call_llm", return_value=reply()) as model:
            self.core.answer_document(text_document("正式员工每年有十天年假。"), "年假？")
        model.assert_called_once()

    def test_no_match_does_not_call_model(self):
        with patch.object(self.core, "call_llm") as model:
            result = self.core.answer_document(text_document("正式员工每年有十天年假。"), "午餐免费吗？")
        self.assertEqual(result.status, "no_match")
        model.assert_not_called()

    def test_high_similarity_does_not_force_answer(self):
        doc = text_document("正式员工每年有十天年假。")
        retriever = Mock()
        retriever.search.return_value = [(doc.text, 0.99)]
        with patch.object(self.core, "call_llm", return_value='{"answerable":false}'):
            result = self.core.answer_document(doc, "午餐免费吗？", retriever)
        self.assertEqual(result.status, "insufficient")

    def test_invalid_rewrite_is_explicit_failure(self):
        history = [Turn("年假？", AnswerResult("十天", "answered"), "关键词检索")]
        with patch.object(self.core, "call_llm", return_value="invalid"):
            with self.assertRaisesRegex(RuntimeError, "追问"):
                self.core.answer_document(text_document("年假十天"), "那他们呢？", history=history)

    def test_failed_turn_is_not_used_as_history(self):
        history = [Turn("年假？", AnswerResult("connection error", "error"), "关键词检索")]
        with patch.object(self.core, "call_llm", return_value=reply()) as model:
            self.core.answer_document(text_document("正式员工每年有十天年假。"), "年假？", history=history)
        model.assert_called_once()


class ChatInterfaceTests(unittest.TestCase):
    def test_history_survives_controls_and_followup_and_resets_on_new_file(self):
        from io import BytesIO
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        import rag_core
        upload = BytesIO("正式员工每年有十天年假。试用期员工没有年假。".encode())
        upload.name = "policy.txt"
        current = [upload]
        with patch.dict("os.environ", {"TENCENT_API_KEY": "test", "TENCENT_API_BASE_URL": "https://example.invalid"}), patch("streamlit.file_uploader", side_effect=lambda *a, **k: current[0]), patch.object(rag_core, "call_llm", side_effect=[reply(), '{"question":"试用期员工有年假吗？"}', reply(text="没有年假", quote="试用期员工没有年假。")]) as model:
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            app.chat_input[0].set_value("年假有几天？").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.chat_message), 2)
            app.sidebar.radio[0].set_value("语义检索").run()
            self.assertEqual(len(app.chat_message), 2)
            next(b for b in app.button if b.label == "清除索引（保留对话）").click().run()
            self.assertEqual(len(app.chat_message), 2)
            self.assertEqual(model.call_count, 1)
            app.sidebar.radio[0].set_value("关键词检索").run()
            app.chat_input[0].set_value("那试用期员工呢？").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.chat_message), 4)
            self.assertEqual(model.call_count, 3)
            self.assertEqual(len(app.get("download_button")), 1)
            current[0] = BytesIO("新文件讲报销。".encode())
            current[0].name = "policy.txt"
            app.run()
            self.assertEqual(len(app.chat_message), 0)
            self.assertEqual(model.call_count, 3)

    def test_failed_request_is_retained_but_not_repeated(self):
        from io import BytesIO
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        import rag_core
        upload = BytesIO("正式员工每年有十天年假。".encode())
        upload.name = "policy.txt"
        with patch.dict("os.environ", {"TENCENT_API_KEY": "test", "TENCENT_API_BASE_URL": "https://example.invalid"}), patch("streamlit.file_uploader", return_value=upload), patch.object(rag_core, "call_llm", side_effect=RuntimeError("模型服务调用失败")) as model:
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            app.chat_input[0].set_value("年假？").run()
            self.assertFalse(app.exception)
            self.assertTrue(any("模型服务调用失败" in e.value for e in app.error))
            app.run()
            self.assertEqual(model.call_count, 1)
            self.assertEqual(len(app.chat_message), 2)
            next(b for b in app.button if b.label == "清空对话").click().run()
            self.assertEqual(len(app.chat_message), 0)


if __name__ == "__main__":
    unittest.main()
