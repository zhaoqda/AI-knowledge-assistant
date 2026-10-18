import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.run import evaluate, load_dataset, score_answer
from evaluation.compare import compare_reports
from grounding import AnswerResult

ROOT = Path(__file__).parent


class ChallengeEvaluationTests(unittest.TestCase):
    def test_challenge_dataset_has_supported_evidence_and_no_duplicate_questions(self):
        data, _ = load_dataset(ROOT / 'evaluation/challenge_cases.json')
        self.assertEqual(len(data['cases']), 20)
        self.assertEqual(len({c['question'] for c in data['cases']}), 20)
        self.assertGreater(len(data['documents']['long_operations']), 3000)
        self.assertTrue(all(c['human_review'] for c in data['cases']))

    def test_dataset_path_is_used_without_model_calls(self):
        with patch('model_services.requests.post') as post:
            report = evaluate(dataset_path=ROOT / 'evaluation/challenge_cases.json', limit=2)
        post.assert_not_called()
        self.assertEqual(report['cases'][0]['id'], 'travel_city_condition')
        self.assertEqual(len(report['implementation_sha256']), 64)

    def test_invalid_dataset_rejected_before_loading_services(self):
        data, _ = load_dataset(ROOT / 'evaluation/challenge_cases.json')
        variants = []
        duplicate = copy.deepcopy(data)
        duplicate['cases'][1]['id'] = duplicate['cases'][0]['id']
        variants.append(duplicate)
        wrong_evidence = copy.deepcopy(data)
        wrong_evidence['cases'][0]['evidence'] = ['不存在的证据']
        variants.append(wrong_evidence)
        no_facts = copy.deepcopy(data)
        no_facts['cases'][0]['facts'] = []
        variants.append(no_facts)
        with tempfile.TemporaryDirectory() as directory, patch('evaluation.run.load_services') as config:
            path = Path(directory) / 'cases.json'
            for value in variants:
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, '数据集无效'):
                    evaluate(answers=True, allow_model_send=True, service_id='a', dataset_path=path)
        config.assert_not_called()

    def test_forbidden_fact_rejects_otherwise_matching_answer(self):
        case = {'answerable': True, 'facts': [['归还电脑']], 'forbidden_facts': ['不需要归还电脑']}
        self.assertFalse(score_answer(AnswerResult('不需要归还电脑', 'answered'), case))
        self.assertTrue(score_answer(AnswerResult('需要归还电脑', 'answered'), case))

    def test_condition_dataset_preserves_old_challenge_and_validates_evidence(self):
        data, _ = load_dataset(ROOT / 'evaluation/condition_cases.json')
        self.assertEqual(len(data['cases']), 8)
        self.assertEqual(sum(c['answerable'] for c in data['cases']), 7)
        old, _ = load_dataset(ROOT / 'evaluation/challenge_cases.json')
        self.assertEqual(len(old['cases']), 20)

    def test_condition_checks_reject_missing_approval_and_operational_limits(self):
        data, _ = load_dataset(ROOT / 'evaluation/condition_cases.json')
        cases = {c['id']: c for c in data['cases']}
        examples = [
            ('late_approval', '不会自动作废。', '不会自动作废，向财务主管说明原因并获得补交批准。'),
            ('guest_approval_followup', '只能延期一次，最长两天。', '只能延期一次，最长两天，经安全管理员批准。'),
            ('read_access_conditions', '说明用途，经数据负责人批准。', '说明用途，经数据负责人批准，五个工作日到期关闭，不允许转借账号。'),
            ('review_privacy_conditions', '服务负责人一个工作日内交复盘报告。', '服务负责人一个工作日内交复盘报告，使用测试账号及脱敏截图，不得包含真实客户密码。'),
        ]
        for id, incomplete, complete in examples:
            with self.subTest(id=id):
                self.assertFalse(score_answer(AnswerResult(incomplete, 'answered'), cases[id]))
                self.assertTrue(score_answer(AnswerResult(complete, 'answered'), cases[id]))

    def test_valid_citation_does_not_imply_complete_conditions(self):
        from documents import text_document, chunk_document
        from grounding import validate_answer
        data, _ = load_dataset(ROOT / 'evaluation/condition_cases.json')
        case = next(c for c in data['cases'] if c['id'] == 'guest_approval_followup')
        chunks = chunk_document(text_document(data['documents']['access']))
        index = next(i for i, c in enumerate(chunks) if '最长两天' in c.text)
        raw = json.dumps({'answerable': True, 'claims': [{'text': '可以延期一次，最长两天。',
                    'source_id': index + 1, 'quote': '最长两天，必须经安全管理员批准'}]})
        result = validate_answer(raw, chunks, case['question'])
        self.assertEqual(result.status, 'answered')
        self.assertFalse(score_answer(result, case))

    def test_condition_retrieval_evaluation_never_sends_model_requests(self):
        with patch('model_services.requests.post') as post:
            report = evaluate(dataset_path=ROOT / 'evaluation/condition_cases.json')
        post.assert_not_called()
        self.assertEqual(report['case_count'], 8)
        self.assertEqual(report['retrieval']['answerable_cases'], 7)

    def report(self):
        return {'live_answers': True, 'dataset_sha256': 'dataset', 'implementation_sha256': 'code', 'mode': 'keyword', 'case_count': 1,
                'service': {'id': 'a', 'model': 'model-a', 'config_fingerprint': 'a'},
                'cases': [{'id': 'one', 'criterion_pass': True, 'status': 'answered'}],
                'summary': {'criterion_passed': 1, 'citation_checks_passed': 1, 'citation_checks_failed': 0, 'service_error_cases': 0, 'call_count': 1, 'median_answer_seconds': 1}}

    def test_compare_rejects_dataset_code_retrieval_or_case_mismatch(self):
        left = self.report()
        for key, value in [('dataset_sha256', 'other'), ('implementation_sha256', 'other'), ('mode', 'semantic'), ('cases', [{'id': 'different', 'criterion_pass': True, 'status': 'answered'}])]:
            right = self.report()
            right['service']['config_fingerprint'] = 'b'
            right[key] = value
            with self.assertRaises(ValueError):
                compare_reports(left, right)
        with self.assertRaises(ValueError):
            compare_reports(left, left)

    def test_compare_outputs_pending_review_and_never_calls_models(self):
        left, right = self.report(), self.report()
        right['service'] = {'id': 'b', 'model': 'model-b', 'config_fingerprint': 'b'}
        with patch('model_services.requests.post') as post:
            result = compare_reports(left, right)
        post.assert_not_called()
        self.assertIn('model-b', result)
        self.assertIn('待核查', result)
        self.assertIn('单次结果不能', result)


if __name__ == '__main__':
    unittest.main()
