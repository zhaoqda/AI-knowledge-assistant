"""Compare two completed reports; never sends requests to a model."""
import argparse
import json
from pathlib import Path


def compare_reports(left, right):
    try:
        for report in (left, right):
            if report['live_answers'] is not True or not report['cases']:
                raise ValueError('报告缺少有效的在线评测内容或服务字段。')
            rows = report['cases']
            ids = [r['id'] for r in rows]
            if len(ids) != len(set(ids)) or report['case_count'] != len(ids):
                raise ValueError('报告缺少有效的在线评测内容或服务字段。')
            if not all(type(r['criterion_pass']) is bool for r in rows):
                raise ValueError('报告缺少有效的在线评测内容或服务字段。')
            for key in ('id', 'model', 'config_fingerprint'):
                if not isinstance(report['service'][key], str) or not report['service'][key]:
                    raise ValueError('报告缺少有效的在线评测内容或服务字段。')
        for key in ('dataset_sha256', 'implementation_sha256', 'mode'):
            if not left[key] or left[key] != right[key]:
                raise ValueError('两份报告的数据集、代码版本或检索方式不同，不能直接对照。')
        if (left.get('source_limit', 3), left.get('review_conditions', False)) != (right.get('source_limit', 3), right.get('review_conditions', False)):
            raise ValueError('两份报告的证据范围或条件核对设置不同，不能直接对照。')
        if [r['id'] for r in left['cases']] != [r['id'] for r in right['cases']]:
            raise ValueError('两份报告题目或顺序不同，不能直接对照。')
        if left['service']['config_fingerprint'] == right['service']['config_fingerprint']:
            raise ValueError('这两份报告来自同一服务配置，不能当作双模型对照。')
        count = left['case_count']
        def cell(value):
            return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
        labels = [cell(r['service']['id'] + ' / ' + r['service']['model']) for r in (left, right)]
        lines = ['# 双模型单次对照', '', '仅比较已有报告，不发起模型调用。单次结果不能判定稳定性能，也不等于产品准确率。',
                 f"数据集 SHA-256：{left['dataset_sha256']}", f"代码 SHA-256：{left['implementation_sha256']}",
                 f"检索方式：{left['mode']}；每组题数：{count}", '',
                 f'| 指标 | {labels[0]} | {labels[1]} |', '| --- | --- | --- |']
        for label, key in [('预设状态与事实检查通过', 'criterion_passed'), ('引用检查通过题数', 'citation_checks_passed'), ('未核验题数', 'citation_checks_failed'), ('服务错误题数', 'service_error_cases'), ('模型调用次数', 'call_count'), ('单题耗时中位数（秒）', 'median_answer_seconds')]:
            lines.append('| ' + label + ' | ' + ' | '.join(cell(r['summary'][key]) for r in (left, right)) + ' |')
        lines.extend(['', f'| 题目 | {labels[0]} | {labels[1]} | 人工核查 |', '| --- | --- | --- | --- |'])
        for a, b in zip(left['cases'], right['cases']):
            values = [cell(a['id'])] + [cell(r['status'] + '；预设检查' + ('通过' if r['criterion_pass'] else '未通过')) for r in (a, b)] + ['待核查']
            lines.append('| ' + ' | '.join(values) + ' |')
        lines.extend(['', '人工重点：适用条件、例外与否定是否保留；引用虽存在但是否支持结论；冲突是否解释；干扰指令是否被执行。',
                      '两组各重复至少三次，并交替运行顺序以减少时间段差异；不据单次结果宣称提升。Token 统计覆盖可能不同，应查看各自原始报告，不能直接把它换算成费用。', ''])
        return '\n'.join(lines)
    except (KeyError, TypeError, AttributeError):
        raise ValueError('报告格式无效，请使用当前版本生成的在线评测报告。') from None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('left', type=Path)
    parser.add_argument('right', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        content = compare_reports(json.loads(args.left.read_text()), json.loads(args.right.read_text()))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding='utf-8')
