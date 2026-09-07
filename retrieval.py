"""Lightweight Chinese and English lexical retrieval; no model downloads required."""

import math
import re
from collections import Counter
from typing import List, Tuple


def _tokens(text: str) -> List[str]:
    tokens = []
    for part in re.findall(r"[\u3400-\u9fff]+|[a-z0-9]+", text.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            # Adjacent character pairs work with Chinese text without spaces.
            tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
            if len(part) == 1:
                tokens.append(part)
        else:
            tokens.append(part)
    return tokens


def simple_retrieve(chunks: List[str], query: str, k: int = 3) -> List[Tuple[str, float]]:
    """Rank matching passages with BM25. Scores are not confidence percentages."""
    if k <= 0 or not chunks:
        return []
    query_terms = set(_tokens(query))
    if not query_terms:
        return []
    documents = [Counter(_tokens(chunk)) for chunk in chunks]
    lengths = [sum(document.values()) for document in documents]
    average_length = sum(lengths) / len(documents)
    if average_length == 0:
        return []
    frequency = Counter(term for document in documents for term in document)
    results = []
    for chunk, document, length in zip(chunks, documents, lengths):
        score = 0.0
        for term in query_terms:
            count = document.get(term, 0)
            if count:
                inverse_frequency = math.log(1 + (len(documents) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += inverse_frequency * count * 2.5 / (count + 1.5 * (0.25 + 0.75 * length / average_length))
        if score > 0:
            results.append((chunk, score))
    return sorted(results, key=lambda item: item[1], reverse=True)[:k]
