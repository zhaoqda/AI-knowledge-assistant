"""Sequential, alternating-order live repeats with immutable per-run reports."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.run import evaluate, render_report, load_dataset
from model_services import load_services


def summarize(reports):
    if not reports:
        raise ValueError('没有可汇总的报告。')
    first = reports[0]
    ids = [c['id'] for c in first['cases']]
    for r in reports:
        if not r.get('live_answers') or not r.get('cases'):
            raise ValueError('重复汇总只接受在线题目报告。')
        if any(r.get(k) != first.get(k) for k in ('dataset_sha256', 'implementation_sha256', 'mode', 'source_limit', 'review_conditions')) or [c['id'] for c in r['cases']] != ids:
            raise ValueError('数据、代码、题目或发送设置不同，不能汇总。')
    groups = {}
    for r in reports:
        service = r['service']
        key = service['config_fingerprint']
        group = groups.setdefault(key, {'service': service, 'reports': []})
        group['reports'].append(r)
    lines = ['# 双模型重复评测', '', '固定开发回归题，多轮交替顺序。模型核对仍可能误报或漏判；不能当作独立语义验收或真实用户准确率。',
             f"数据集：{first['dataset_sha256']}", f"代码：{first['implementation_sha256']}",
             f"候选上限：{first['source_limit']}；条件核对：{first['review_conditions']}", '',
             '| 服务 / 模型 | 轮次 | 预设检查通过 / 总题次 | 条件核对拦截 | 核对无效 | 服务错误 | 调用次数 | 单题耗时中位数（秒） |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for group in groups.values():
        runs = group['reports']; rows = [c for r in runs for c in r['cases']]
        service = group['service']; states = Counter(c.get('review_status') for c in rows)
        label = (service['id'] + ' / ' + service['model']).replace('|', '\\|')
        lines.append(f"| {label} | {len(runs)} | {sum(c['criterion_pass'] for c in rows)}/{len(rows)} | {states['flagged']} | {states['invalid']} | {sum(c['status']=='error' for c in rows)} | {sum(r['summary']['call_count'] for r in runs)} | {median(c['answer_seconds'] for c in rows):.3f} |")
    for group in groups.values():
        runs = group['reports']; rows = [c for r in runs for c in r['cases']]
        service = group['service']
        label = (service['id'] + ' / ' + service['model']).replace('|', '\\|')
        lines.extend(['', f'## {label} 逐题重复结果', '', '| 题号 | 通过 / 次数 | 状态计数 |', '| --- | --- | --- |'])
        for id in ids:
            matching = [c for c in rows if c['id'] == id]
            lines.append(f"| {id} | {sum(c['criterion_pass'] for c in matching)}/{len(matching)} | {dict(Counter(c['status'] for c in matching))} |")
        lines.append('')
    lines.extend(['同一道题多次运行不是独立用户样本；汇总不证明统计显著性。被拦截代表未向用户显示为可靠答案，不代表任务已完成。需复核拦截是否合理、通过答案是否仍有遗漏。', ''])
    return '\n'.join(lines)


def run_repeated(dataset, service_ids, rounds, output):
    if not 1 <= rounds <= 3 or len(service_ids) < 2 or len(set(service_ids)) != len(service_ids):
        raise ValueError('轮次为 1—3，至少两个不同服务。')
    configs = {s.id: s for s in load_services()}
    if any(s not in configs or not configs[s].configured for s in service_ids):
        raise ValueError('服务或密钥未配置，评测未开始。')
    load_dataset(dataset)
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    for round_index in range(rounds):
        order = service_ids if round_index % 2 == 0 else list(reversed(service_ids))
        for service in order:
            report = evaluate(answers=True, service_id=service, allow_model_send=True,
                dataset_path=dataset, source_limit=6, review_conditions=True,
                notify=lambda row: print(f"round {round_index+1} {service} {row['id']} {row['status']}", flush=True))
            stem = output/f'round-{round_index+1}-{service}'
            stem.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            stem.with_suffix('.md').write_text(render_report(report), encoding='utf-8')
            reports.append(report)
            (output/'summary.md').write_text(summarize(reports), encoding='utf-8')
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--services', nargs='+', required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-model-send', action='store_true')
    args = parser.parse_args()
    if not args.allow_model_send:
        parser.error('在线重复评测需要 --allow-model-send，会产生计费请求。')
    try:
        run_repeated(args.dataset, args.services, args.rounds, args.output)
    except (ValueError, FileExistsError):
        parser.error('评测配置无效、不可比较或输出目录已存在；请检查配置并使用新目录。')
