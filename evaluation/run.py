"""Reproducible development evaluation; live answer calls require --answers."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
from statistics import median
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conversation import Conversation, Turn
from model_services import ModelSession, load_services
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
        for group in case.get("facts", [])) and not any(
            normalized(value) in normalized(result.answer) for value in case.get("forbidden_facts", []))


def load_dataset(path):
    try:
        data_bytes = Path(path).read_bytes()
        dataset = json.loads(data_bytes)
        documents = dataset["documents"]
        cases = dataset["cases"]
        if not isinstance(documents, dict) or not documents or not isinstance(cases, list) or not cases:
            raise ValueError()
        if not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in documents.items()):
            raise ValueError()
        ids = set()
        for case in cases:
            if not isinstance(case["id"], str) or not case["id"] or case["id"] in ids:
                raise ValueError()
            ids.add(case["id"])
            if case["document"] not in documents or type(case["answerable"]) is not bool:
                raise ValueError()
            if not isinstance(case["question"], str) or not 1 <= len(case["question"].strip()) <= 400:
                raise ValueError()
            if not isinstance(case["category"], str):
                raise ValueError()
            if not isinstance(case.get("history", []), list) or not all(isinstance(x, str) and 1 <= len(x.strip()) <= 400 for x in case.get("history", [])):
                raise ValueError()
            if "standalone_query" in case and (not isinstance(case["standalone_query"], str) or not 1 <= len(case["standalone_query"].strip()) <= 400):
                raise ValueError()
            evidence = case.get("evidence", [])
            facts = case.get("facts", [])
            forbidden = case.get("forbidden_facts", [])
            if not isinstance(evidence, list) or not all(isinstance(x, str) and x.strip() and normalized(x) in normalized(documents[case["document"]]) for x in evidence):
                raise ValueError()
            if not isinstance(facts, list) or not all(isinstance(g, list) and g and all(isinstance(x, str) and x.strip() for x in g) for g in facts):
                raise ValueError()
            if case["answerable"] and (not evidence or not facts):
                raise ValueError()
            if not isinstance(forbidden, list) or not all(isinstance(x, str) and x.strip() for x in forbidden):
                raise ValueError()
        if not isinstance(dataset["description"], str):
            raise ValueError()
        return dataset, data_bytes
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("评测数据集无效：请检查文档、唯一题号、问题、证据及事实检查字段。") from None


def evaluate(mode="keyword", answers=False, limit=None, notify=None,
             service_id=None, allow_model_send=False, dataset_path=None, source_limit=3, review_conditions=False):
    if source_limit not in (3, 6):
        raise ValueError("候选原文数量只能为 3 或 6。")
    answer_options = {} if source_limit == 3 and not review_conditions else {"source_limit": source_limit, "review_conditions": review_conditions}
    if mode not in {"keyword", "semantic"}:
        raise ValueError("检索方式必须为 keyword 或 semantic。")
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError("评测题数必须为正整数。")
    dataset, dataset_bytes = load_dataset(dataset_path or ROOT / "evaluation/cases.json")
    service = None
    session = ModelSession()
    if answers:
        if not allow_model_send:
            raise ValueError("在线评测需要显式允许发送指定评测资料与问答（--allow-model-send）。")
        if not service_id:
            raise ValueError("在线评测必须指定部署配置中的服务（--service）。")
        service = next((s for s in load_services() if s.id == service_id), None)
        if service is None:
            raise ValueError("未找到指定服务，请检查部署服务配置。")
        if not service.configured:
            raise ValueError("指定服务未配置密钥，评测未开始。")
    elif service_id or allow_model_send:
        raise ValueError("--service 和 --allow-model-send 只用于 --answers 在线评测。")
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
            found = retriever.search(texts, query, k=source_limit) if retriever else simple_retrieve(texts, query, k=source_limit)
            retrieved = normalized("\n".join(text for text, _ in found))
            evidence = case.get("evidence", [])
            row = {"id": case["id"], "category": case["category"], "question": case["question"],
                   "answerable": case["answerable"],
                   "retrieval_all_evidence": all(normalized(s) in retrieved for s in evidence) if evidence else None,
                   "retrieval_seconds": round(perf_counter() - start, 3)}
            if answers:
                history = []
                document_id = Conversation.key_for(document.text.encode(), document.filename)
                session.approve(service, document_id)
                record_start = len(session.records)
                model_call = lambda prompt, phase, chunks: session.call(
                    service, document_id, prompt, phase, chunks)
                start = perf_counter()
                try:
                    for previous in case.get("history", []):
                        previous_result = answer_document(document, previous, retriever, model_call=model_call, **answer_options)
                        if previous_result.status != "answered":
                            raise RuntimeError("评测前置问题未成功回答")
                        history.append(Turn(previous, previous_result, mode))
                    result = answer_document(document, case["question"], retriever, history, model_call=model_call, **answer_options)
                except Exception:
                    result = AnswerResult("服务或评测前置问题失败", "error")
                calls = session.records[record_start:]
                row.update(reviewed_answer=result.reviewed_answer, reason_code=result.reason_code, review_status=result.review_status, review_notes=list(result.review_notes), call_ids=[r["call_id"] for r in calls],
                           call_count=len(calls),
                           citation_check="passed" if result.status == "answered" or result.review_status in {"passed", "flagged", "invalid"} else
                               "failed" if result.status == "unverified" else "not_applicable",
                           cited_source_count=len(result.sources),
                           status=result.status, answer=result.answer,
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
              "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
              "implementation_sha256": hashlib.sha256(b"".join(
                  (ROOT / name).read_bytes() for name in
                  ("rag_core.py", "documents.py", "retrieval.py", "vector_retrieval.py", "grounding.py", "model_services.py", "answer_checks.py", "evaluation/run.py"))).hexdigest(),
              "description": dataset["description"], "case_count": len(rows),
              "source_limit": source_limit, "review_conditions": review_conditions,
              "retrieval": {"all_evidence_hits": sum(r["retrieval_all_evidence"] for r in retrieval_cases),
                            "answerable_cases": len(retrieval_cases)}, "cases": rows}
    if answers:
        times = [r["answer_seconds"] for r in rows]
        report["service"] = {"id": service.id, "provider": service.provider,
                             "model": service.model, "endpoint": service.base_url,
                             "config_fingerprint": service.fingerprint}
        report["calls"] = session.records
        report["summary"] = {
            "criterion_passed": sum(r["criterion_pass"] for r in rows),
            "citation_checks_passed": sum(r["citation_check"] == "passed" for r in rows),
            "citation_checks_failed": sum(r["citation_check"] == "failed" for r in rows),
            "service_error_cases": sum(r["status"] == "error" for r in rows),
            "call_count": len(session.records),
            "successful_calls": sum(r["status"] == "success" for r in session.records),
            "median_answer_seconds": round(median(times), 3) if times else None,
            "usage_reported_calls": sum("usage" in r for r in session.records),
            "token_reporting_coverage": {key: sum(key in r.get("usage", {}) for r in session.records)
                                         for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
            "reported_tokens": {key: sum(r.get("usage", {}).get(key, 0) for r in session.records)
                                if any(key in r.get("usage", {}) for r in session.records) else None
                                for key in ("prompt_tokens", "completion_tokens", "total_tokens")}}
        report["statuses"] = dict(Counter(r["status"] for r in rows))
        report["by_category"] = {category: {"passed": sum(r["criterion_pass"] for r in rows if r["category"] == category),
                                             "total": sum(r["category"] == category for r in rows)}
                                  for category in dict.fromkeys(r["category"] for r in rows)}
    return report


def render_report(report):
    """Human-readable summary, without copying answer or source text."""
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    retrieval = report["retrieval"]
    lines = ["# 文档问答开发评测报告", "", f"时间（UTC）：{report['timestamp']}",
             f"检索方式：{report['mode']}；题数：{report['case_count']}；最多原文：{report.get('source_limit', 3)}；条件核对：{report.get('review_conditions', False)}",
             f"数据集 SHA-256：{report['dataset_sha256']}", "",
             cell(report["description"]),
             "事实字符串检查不等于完整语义正确性或产品准确率。",
             f"全部指定证据进入前 {report.get('source_limit', 3)} 处：{retrieval['all_evidence_hits']}/{retrieval['answerable_cases']}", ""]
    if report["live_answers"]:
        service = report["service"]
        summary = report["summary"]
        lines.extend([f"服务：{cell(service['id'])}；提供方：{cell(service['provider'])}；模型：{cell(service['model'])}",
            f"端点：{cell(service['endpoint'])}",
            f"服务配置指纹：{service['config_fingerprint']}", "",
            f"预设状态与事实检查通过：{summary['criterion_passed']}/{report['case_count']}",
            f"引用检查通过：{summary['citation_checks_passed']}；未核验：{summary['citation_checks_failed']}；服务错误题：{summary['service_error_cases']}",
            f"模型调用：{summary['call_count']} 次；请求返回有效正文：{summary['successful_calls']} 次",
            f"单题总耗时中位数：{summary['median_answer_seconds']} 秒（含前置问答和改写）", ""])
        for key, label in [("prompt_tokens", "输入"), ("completion_tokens", "输出"), ("total_tokens", "总计")]:
            value = summary["reported_tokens"][key]
            lines.append(f"{label} Token：{value if value is not None else '未提供'}；覆盖 {summary['token_reporting_coverage'][key]}/{summary['call_count']} 次调用")
        lines.extend(["", "Token 是服务报告值，可能只覆盖部分请求；不代表账单金额。引用检查只验证结构、来源编号和摘句存在，不证明结论解释正确。", ""])
    else:
        lines.extend(["本次只做检索，不发送问题或原文给回答模型。语义模式首次加载仍可能下载向量模型。", ""])
    lines.extend(["| 题目 | 检索证据 | 回答状态 | 预设检查 | 引用检查 | 调用次数 | 总耗时（秒） |",
                  "| --- | --- | --- | --- | --- | --- | --- |"])
    for row in report["cases"]:
        evidence = row["retrieval_all_evidence"]
        values = [row["id"], "不适用" if evidence is None else "命中" if evidence else "未全命中",
                  row.get("status", "未运行回答"), "通过" if row.get("criterion_pass") else "未通过" if "criterion_pass" in row else "—",
                  row.get("citation_check", "—"), row.get("call_count", "—"), row.get("answer_seconds", "—")]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines.extend(["", "对照模型时需使用相同数据集指纹、题目集合、检索方式与发送设置，多次重复并人工核查回答和适用条件。单次结果不证明模型优劣。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["keyword", "semantic"], default="keyword")
    parser.add_argument("--source-limit", type=int, choices=[3, 6], default=3)
    parser.add_argument("--review-conditions", action="store_true")
    parser.add_argument("--answers", action="store_true", help="Call the configured paid answer service")
    parser.add_argument("--dataset", type=Path, help="Evaluation dataset JSON path")
    parser.add_argument("--service", help="Deployment-approved service id")
    parser.add_argument("--allow-model-send", action="store_true",
                        help="Allow sending the selected evaluation documents, questions and history")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path, help="Save a readable report")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    try:
        report = evaluate(args.mode, args.answers, args.limit,
                          notify=lambda row: print(row["id"], row.get("status", "retrieval only"), file=sys.stderr, flush=True),
                          service_id=args.service, allow_model_send=args.allow_model_send, dataset_path=args.dataset, source_limit=args.source_limit, review_conditions=args.review_conditions)
    except ValueError as exc:
        parser.error(str(exc))
    content = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n")
    else:
        print(content)

    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_report(report), encoding="utf-8")
