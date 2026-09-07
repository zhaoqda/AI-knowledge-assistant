"""Reproducible development evaluation; live answer calls require --answers."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conversation import Turn
from documents import chunk_document, text_document, unique_chunks
from grounding import AnswerResult
from rag_core import answer_document
from retrieval import simple_retrieve


def normalized(text):
    return "".join(text.split())


def score_answer(result, case):
    if not case["answerable"]:
        return result.status in {"no_match", "insufficient"}
    return result.status == "answered" and all(
        any(normalized(option) in normalized(result.answer) for option in group)
        for group in case.get("facts", []))


def evaluate(mode="keyword", answers=False, limit=None, notify=None):
    dataset = json.loads((ROOT / "evaluation/cases.json").read_text())
    cases = dataset["cases"][:limit]
    retriever = None
    if mode == "semantic":
        from vector_retrieval import LocalEmbedder, VectorRetriever
        retriever = VectorRetriever(LocalEmbedder())
    rows = []
    try:
        for case in cases:
            document = text_document(dataset["documents"][case["document"]], case["document"] + ".txt")
            chunks = unique_chunks(chunk_document(document))
            query = case.get("standalone_query", case["question"])
            start = perf_counter()
            texts = [chunk.text for chunk in chunks]
            found = retriever.search(texts, query, k=3) if retriever else simple_retrieve(texts, query, k=3)
            retrieved = normalized("\n".join(text for text, _ in found))
            evidence = case.get("evidence", [])
            row = {"id": case["id"], "category": case["category"], "question": case["question"],
                   "answerable": case["answerable"],
                   "retrieval_all_evidence": all(normalized(s) in retrieved for s in evidence) if evidence else None,
                   "retrieval_seconds": round(perf_counter() - start, 3)}
            if answers:
                history = []
                start = perf_counter()
                try:
                    for previous in case.get("history", []):
                        previous_result = answer_document(document, previous, retriever)
                        if previous_result.status != "answered":
                            raise RuntimeError("评测前置问题未成功回答")
                        history.append(Turn(previous, previous_result, mode))
                    result = answer_document(document, case["question"], retriever, history)
                except Exception:
                    result = AnswerResult("服务或评测前置问题失败", "error")
                row.update(status=result.status, answer=result.answer,
                           resolved_question=result.retrieval_query,
                           criterion_pass=score_answer(result, case),
                           answer_seconds=round(perf_counter() - start, 3))
            rows.append(row)
            if notify:
                notify(row)
    finally:
        if retriever:
            retriever.clear()
    retrieval_cases = [r for r in rows if r["retrieval_all_evidence"] is not None]
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "mode": mode, "live_answers": answers,
              "description": dataset["description"], "case_count": len(rows),
              "retrieval": {"all_evidence_hits": sum(r["retrieval_all_evidence"] for r in retrieval_cases),
                            "answerable_cases": len(retrieval_cases)}, "cases": rows}
    if answers:
        report["statuses"] = dict(Counter(r["status"] for r in rows))
        report["by_category"] = {category: {"passed": sum(r["criterion_pass"] for r in rows if r["category"] == category),
                                             "total": sum(r["category"] == category for r in rows)}
                                  for category in dict.fromkeys(r["category"] for r in rows)}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["keyword", "semantic"], default="keyword")
    parser.add_argument("--answers", action="store_true", help="Call the configured paid answer service")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    report = evaluate(args.mode, args.answers, args.limit,
                      notify=lambda row: print(row["id"], row.get("status", "retrieval only"), file=sys.stderr, flush=True))
    content = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n")
    else:
        print(content)
