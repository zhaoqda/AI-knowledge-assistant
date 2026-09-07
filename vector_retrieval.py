"""Session-owned vector index with explicit embedding and cosine distance."""

import hashlib
import json
import uuid
from pathlib import Path
from threading import Lock


class LocalEmbedder:
    MODEL = "BAAI/bge-small-zh-v1.5"

    def __init__(self):
        self.lock = Lock()
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(
            self.MODEL,
            cache_folder=str(Path(__file__).parent / ".model_cache"),
            device="cpu",
        )

    def __call__(self, texts):
        lengths = [len(self.model.tokenizer.encode(text)) for text in texts]
        if any(length > self.model.max_seq_length for length in lengths):
            raise ValueError("文本片段超过向量模型长度限制，请缩短问题或减小分块长度。")
        with self.lock:
            return self.model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()

    def encode_query(self, question):
        return self(["为这个句子生成表示以用于检索相关文章：" + question])


class VectorRetriever:
    def __init__(self, embedder, client=None):
        if client is None:
            import chromadb
            from chromadb.config import Settings
            client = chromadb.EphemeralClient(Settings(anonymized_telemetry=False))
        self.client = client
        self.embedder = embedder
        self.collection = None
        self.document_key = None

    def search(self, chunks, question, k=3):
        chunks = [chunk for chunk in chunks if chunk.strip()]
        if not chunks or not question.strip() or k <= 0:
            return []
        document_key = hashlib.sha256(json.dumps(chunks, ensure_ascii=False).encode()).hexdigest()
        if document_key != self.document_key:
            vectors = self.embedder(chunks)
            collection = self.client.create_collection(
                name="document-" + uuid.uuid4().hex,
                embedding_function=None,
                configuration={"hnsw": {"space": "cosine"}},
            )
            try:
                collection.add(
                    ids=[str(i) for i in range(len(chunks))],
                    documents=chunks,
                    embeddings=vectors,
                )
            except Exception:
                self.client.delete_collection(collection.name)
                raise
            self.clear()
            self.collection = collection
            self.document_key = document_key
        query_vectors = (self.embedder.encode_query(question)
                         if hasattr(self.embedder, "encode_query") else self.embedder([question]))
        result = self.collection.query(
            query_embeddings=query_vectors,
            n_results=min(k, len(chunks)),
            include=["documents", "distances"],
        )
        # A high similarity is not evidence that the passage answers the question.
        return list(zip(result["documents"][0], [1 - distance for distance in result["distances"][0]]))

    def clear(self):
        if self.collection is not None:
            self.client.delete_collection(self.collection.name)
        self.collection = None
        self.document_key = None
