import unittest
from vector_retrieval import VectorRetriever


class Embeddings:
    def __init__(self):
        self.calls = []

    def __call__(self, texts):
        self.calls.append(list(texts))
        values = {
            "试用期为三个月。": [1.0, 0.0, 0.0],
            "多久转正？": [0.99, 0.01, 0.0],
            "报销需要发票。": [0.0, 1.0, 0.0],
            "另一个文档": [0.0, 0.0, 1.0],
        }
        return [values[text] for text in texts]


class VectorTests(unittest.TestCase):
    def setUp(self):
        self.embedder = Embeddings()
        self.retriever = VectorRetriever(self.embedder)
        self.chunks = ["报销需要发票。", "试用期为三个月。"]

    def tearDown(self):
        self.retriever.clear()

    def test_cosine_ranking_with_controlled_vectors(self):
        result = self.retriever.search(self.chunks, "多久转正？")
        self.assertEqual(result[0][0], self.chunks[1])
        self.assertGreater(result[0][1], 0.99)

    def test_same_document_reuses_embeddings(self):
        self.retriever.search(self.chunks, "多久转正？")
        self.retriever.search(self.chunks, "多久转正？")
        self.assertEqual(sum(call == self.chunks for call in self.embedder.calls), 1)

    def test_switching_documents_replaces_index(self):
        self.retriever.search(self.chunks, "多久转正？")
        original_name = self.retriever.collection.name
        result = self.retriever.search(["另一个文档"], "多久转正？")
        self.assertEqual([text for text, _ in result], ["另一个文档"])
        self.assertNotIn(original_name, [c.name for c in self.retriever.client.list_collections()])

    def test_sessions_do_not_share_collections(self):
        other = VectorRetriever(self.embedder, client=self.retriever.client)
        try:
            self.retriever.search(self.chunks, "多久转正？")
            other.search(["另一个文档"], "多久转正？")
            self.assertNotEqual(other.collection.name, self.retriever.collection.name)
            self.assertEqual(self.retriever.collection.count(), 2)
        finally:
            other.clear()

    def test_empty_input_skips_embedding(self):
        self.assertEqual(self.retriever.search([], "多久转正？"), [])
        self.assertEqual(self.embedder.calls, [])

    def test_query_specific_encoder_is_used(self):
        queries = []

        def encode_query(question):
            queries.append(question)
            return self.embedder([question])

        self.embedder.encode_query = encode_query
        self.retriever.search(self.chunks, "多久转正？")
        self.assertEqual(queries, ["多久转正？"])


if __name__ == "__main__":
    unittest.main()
