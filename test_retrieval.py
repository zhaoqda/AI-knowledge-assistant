import unittest
import json
from unittest.mock import patch

from retrieval import simple_retrieve


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            "本公司主要销售办公用品。",
            "员工每年可以享受十天带薪年假。",
            "报销申请需要提供发票。",
            "试用期为三个月。",
        ]

    def test_chinese_answer_beyond_first_three_passages(self):
        results = simple_retrieve(self.chunks, "试用期多长？")
        self.assertEqual(results[0][0], self.chunks[3])

    def test_chinese_annual_leave(self):
        self.assertEqual(simple_retrieve(self.chunks, "年假有几天？")[0][0], self.chunks[1])

    def test_unmatched_question_returns_no_passages(self):
        self.assertEqual(simple_retrieve(self.chunks, "免费午餐？"), [])

    def test_english_case_and_punctuation(self):
        self.assertEqual(simple_retrieve(["Office supplies.", "Annual LEAVE: ten days."], "leave?")[0][0], "Annual LEAVE: ten days.")

    def test_empty_inputs(self):
        for chunks, query, k in [([], "年假", 3), (self.chunks, "？", 3), (self.chunks, "年假", 0), ([""], "年假", 3)]:
            self.assertEqual(simple_retrieve(chunks, query, k), [])

    def test_top_k(self):
        self.assertEqual(len(simple_retrieve(["年假十天", "年假五天"], "年假", 1)), 1)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Do not load local credentials or call paid services in these tests.
        with patch("dotenv.load_dotenv"):
            import rag_core
        cls.core = rag_core

    def test_no_match_skips_model(self):
        with patch.object(self.core, "call_llm") as model:
            answer, sources = self.core.rag_query("试用期为三个月。", "免费午餐？")
        self.assertEqual(sources, [])
        self.assertIn("未检索到", answer)
        model.assert_not_called()

    def test_matching_query_preserves_interface(self):
        with patch.object(self.core, "call_llm", return_value=json.dumps({"answerable": True, "claims": [{"text": "三个月", "source_id": 1, "quote": "试用期为三个月。"}]})):
            answer, sources = self.core.rag_query("试用期为三个月。", "试用期多久？")
        self.assertEqual(answer, "三个月 [来源1]")
        self.assertEqual(sources, ["试用期为三个月。"])

    def test_vector_retriever_is_used_when_selected(self):
        from unittest.mock import Mock
        retriever = Mock()
        retriever.search.return_value = [("试用期为三个月。", 0.8)]
        with patch.object(self.core, "call_llm", return_value=json.dumps({"answerable": True, "claims": [{"text": "三个月", "source_id": 1, "quote": "试用期为三个月。"}]})), patch.object(self.core, "simple_retrieve") as keyword:
            answer, sources = self.core.rag_query("试用期为三个月。", "多久转正？", retriever=retriever)
        self.assertEqual(answer, "三个月 [来源1]")
        self.assertEqual(sources, ["试用期为三个月。"])
        retriever.search.assert_called_once()
        keyword.assert_not_called()

    def test_service_failure_is_an_exception(self):
        with patch.object(self.core, "API_KEY", "test"), patch.object(self.core, "BASE_URL", "https://example.invalid"), patch.object(self.core.requests, "post", side_effect=RuntimeError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "模型服务调用失败"):
                self.core.call_llm("test")


if __name__ == "__main__":
    unittest.main()
