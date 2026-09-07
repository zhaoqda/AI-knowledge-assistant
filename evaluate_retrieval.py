"""Small synthetic retrieval comparison, not a general accuracy benchmark."""

import json

from retrieval import simple_retrieve
from vector_retrieval import LocalEmbedder, VectorRetriever


CASES = [
    ("新员工试用期为三个月。", "多久转正？"),
    ("正式员工每年享有十天带薪年假。", "一年能休多少天假？"),
    ("报销需要正规发票，费用发生后三十天内提交申请。", "垫付的钱怎样找公司报回来？"),
    ("每人每年有三千元学习预算，用于购买专业书籍或参加课程。", "公司给进修提供多少资金？"),
    ("正式员工每周最多可以远程办公两天。", "一星期可以几天不去办公室上班？"),
    ("员工应在上午九点至十点之间到岗，每天工作八小时。", "每天最迟几点打卡上班？"),
]


def evaluate():
    chunks = [passage for passage, _ in CASES]
    retriever = VectorRetriever(LocalEmbedder())
    results = []
    try:
        for expected, question in CASES:
            keyword = [text for text, _ in simple_retrieve(chunks, question)]
            semantic = [text for text, _ in retriever.search(chunks, question)]
            results.append({
                "question": question,
                "expected": expected,
                "keyword_top1": keyword[:1] == [expected],
                "semantic_top1": semantic[:1] == [expected],
                "keyword_top3": expected in keyword,
                "semantic_top3": expected in semantic,
                "semantic_results": semantic,
            })
    finally:
        retriever.clear()
    return {
        "sample_count": len(CASES),
        "hits": {key: sum(row[key] for row in results) for key in
                 ["keyword_top1", "semantic_top1", "keyword_top3", "semantic_top3"]},
        "cases": results,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
