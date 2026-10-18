import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from documents import text_document, chunk_document
from grounding import AnswerResult
from answer_checks import check_conditions, explain_refusal
from rag_core import answer_document, retrieve_document
from send_preview import PreviewFlow, PreviewRequired
from evaluation.run import evaluate, load_dataset
from evaluation.compare import compare_reports

ROOT = Path(__file__).parent


class TrustFlowTests(unittest.TestCase):
    def setUp(self):
        self.doc = text_document('访客延期最长两天，必须经安全管理员批准。')
        self.sources = chunk_document(self.doc)
        self.result = AnswerResult('访客延期最长两天。 [来源1]', 'answered', tuple(self.sources))

    def test_review_flags_supported_approval_omission(self):
        call = Mock(return_value=json.dumps({'complete': False, 'issues': [
            {'source_id': 1, 'quote': '必须经安全管理员批准', 'reason': '遗漏批准要求'}]}))
        result = check_conditions(self.result, self.sources, '延期多久？', call, ['hash'])
        self.assertEqual(result.status, 'unverified')
        self.assertFalse(result.sources)
        self.assertEqual(result.candidates, tuple(self.sources))
        self.assertNotIn('最长两天', result.answer)
        self.assertEqual(call.call_args.args[1], 'review')

    def test_review_ignores_display_citation_renumbering_and_preserves_flagged_draft(self):
        call = Mock(return_value='{"complete":false,"issues":[{"source_id":1,"quote":"必须经安全管理员批准","reason":"遗漏审批"}]}')
        result = check_conditions(self.result, self.sources, '多久？', call, [])
        self.assertNotIn('[来源1]', call.call_args.args[0])
        self.assertEqual(result.reviewed_answer, self.result.answer)
        self.assertNotEqual(result.answer, result.reviewed_answer)

    def test_review_rejects_fabricated_quotes_and_invalid_contracts(self):
        values = [{'complete': True, 'issues': [1]}, {'complete': 'yes', 'issues': []},
                  {'complete': False, 'issues': []},
                  {'complete': False, 'issues': [{'source_id': 1, 'quote': '不存在的审批规则', 'reason': 'missing'}]},
                  {'complete': False, 'issues': [{'source_id': True, 'quote': '必须经安全管理员批准', 'reason': 'missing'}]}]
        for value in values:
            with self.subTest(value=value):
                result = check_conditions(self.result, self.sources, '延期多久？', lambda *a: json.dumps(value), [])
                self.assertEqual(result.review_status, 'invalid')
                self.assertEqual(result.status, 'unverified')

    def test_review_success_does_not_change_answer_and_is_labeled(self):
        result = check_conditions(self.result, self.sources, '多久？', lambda *a: '{"complete":true,"issues":[]}', [])
        self.assertEqual(result.answer, self.result.answer)
        self.assertEqual(result.review_status, 'passed')

    def test_review_is_optional_and_not_used_on_refusal(self):
        for review in (True, False):
            caller = Mock(return_value='{"answerable":false,"reason_code":"missing_information"}')
            result = answer_document(self.doc, '访客延期？', model_call=caller, review_conditions=review)
            self.assertEqual(caller.call_count, 1)
            self.assertEqual(result.reason_code, 'missing_information')

    def test_answer_then_review_routes_once_per_phase(self):
        caller = Mock(side_effect=[json.dumps({'answerable': True, 'claims': [{'text': '延期最长两天。',
            'source_id': 1, 'quote': '访客延期最长两天'}]}), '{"complete":true,"issues":[]}'])
        result = answer_document(self.doc, '访客延期多久？', model_call=caller, review_conditions=True)
        self.assertEqual(result.review_status, 'passed')
        self.assertEqual([c.args[1] for c in caller.call_args_list], ['answer', 'review'])

    def test_refusal_categories_do_not_echo_untrusted_reason(self):
        for code in ['missing_personal_context', 'conflicting_sources', 'missing_information', 'UNKNOWN_SECRET']:
            result = explain_refusal(json.dumps({'reason_code': code}), AnswerResult('不足', 'insufficient'))
            self.assertTrue(result.next_step)
            self.assertNotIn('SECRET', result.answer + result.reason_code)

    def test_bounded_expansion_covers_long_cross_section_evidence(self):
        data, _ = load_dataset(ROOT/'evaluation/challenge_cases.json')
        case = next(c for c in data['cases'] if c['id'] == 'long_multi_conditions')
        doc = text_document(data['documents'][case['document']])
        base = '\n'.join(c.text for c in retrieve_document(doc, case['question'], source_limit=3))
        expanded = retrieve_document(doc, case['question'], source_limit=6)
        text = '\n'.join(c.text for c in expanded)
        self.assertFalse(all(e in base for e in case['evidence']))
        self.assertTrue(all(e in text for e in case['evidence']))
        self.assertLessEqual(len(expanded), 6)
        with self.assertRaises(ValueError):
            retrieve_document(doc, case['question'], source_limit=7)

    def test_preview_requires_each_exact_payload_and_replays_without_resending(self):
        flow = PreviewFlow('追问', ('doc', 'service'), 0)
        sender = Mock(side_effect=['rewritten', 'answer'])
        with self.assertRaises(PreviewRequired):
            flow.call('history', 'rewrite', [], sender)
        sender.assert_not_called()
        flow.approve(); flow.begin()
        self.assertEqual(flow.call('history', 'rewrite', [], sender), 'rewritten')
        with self.assertRaises(PreviewRequired):
            flow.call('document', 'answer', ['hash'], sender)
        self.assertEqual(sender.call_count, 1)
        flow.approve(); flow.begin()
        self.assertEqual(flow.call('history', 'rewrite', [], sender), 'rewritten')
        self.assertEqual(flow.call('document', 'answer', ['hash'], sender), 'answer')
        self.assertEqual(sender.call_count, 2)

    def test_preview_payload_change_invalidates_approval(self):
        flow = PreviewFlow('q', ('doc', 'service'), 0)
        sender = Mock(return_value='ok')
        with self.assertRaises(PreviewRequired):
            flow.call('original', 'answer', [], sender)
        flow.approve(); flow.begin()
        with self.assertRaises(PreviewRequired):
            flow.call('changed', 'answer', [], sender)
        sender.assert_not_called()

    def test_interface_preview_cancels_without_sending_and_settings_invalidate(self):
        from streamlit.testing.v1 import AppTest
        import os
        with patch.dict(os.environ, {'TENCENT_API_KEY': 'test', 'TENCENT_API_BASE_URL': 'https://example.invalid/v1', 'MODEL_SERVICES_CONFIG': ''}), patch('model_services.requests.post') as post:
            app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
            app.toggle[0].set_value(True).run()
            next(b for b in app.button if b.label == '确认接收方并允许当前文档问答').click().run()
            next(c for c in app.checkbox if c.label == '每次发送前查看内容').check().run()
            app.chat_input[0].set_value('年假几天？').run()
            self.assertFalse(app.exception)
            self.assertTrue(app.chat_input[0].disabled)
            self.assertTrue(any(b.label == '确认发送本次内容' for b in app.button))
            post.assert_not_called()
            next(c for c in app.checkbox if c.label == '回答后核对关键条件').check().run()
            self.assertNotIn('preview_flow', app.session_state)
            post.assert_not_called()

    def test_interface_preview_confirm_sends_once_and_finishes_turn(self):
        from streamlit.testing.v1 import AppTest
        from test_model_services import response
        import os
        with patch.dict(os.environ, {'TENCENT_API_KEY': 'test', 'TENCENT_API_BASE_URL': 'https://example.invalid/v1', 'MODEL_SERVICES_CONFIG': ''}), patch('model_services.requests.post', return_value=response()) as post:
            app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
            app.toggle[0].set_value(True).run()
            next(b for b in app.button if b.label == '确认接收方并允许当前文档问答').click().run()
            next(c for c in app.checkbox if c.label == '每次发送前查看内容').check().run()
            app.chat_input[0].set_value('年假几天？').run()
            preview = app.session_state.preview_flow.pending['prompt']
            post.assert_not_called()
            next(b for b in app.button if b.label == '确认发送本次内容').click().run()
            self.assertEqual(post.call_count, 1)
            self.assertEqual(post.call_args.kwargs['json']['messages'][0]['content'], preview)
            self.assertEqual(len(app.session_state.conversation.turns), 1)
            self.assertNotIn('preview_flow', app.session_state)
            self.assertFalse(app.exception)

    def test_evaluation_keeps_condition_interception_separate_from_citation_failure(self):
        from test_model_services import service
        import os
        blocked = AnswerResult('条件核对拦截', 'unverified', review_status='flagged')
        with patch('evaluation.run.load_services', return_value=[service()]), patch.dict(os.environ, {'TEST_SERVICE_KEY': 'test'}), patch('evaluation.run.answer_document', return_value=blocked):
            report = evaluate(answers=True, service_id='a', allow_model_send=True, limit=1)
        self.assertEqual(report['cases'][0]['citation_check'], 'passed')
        self.assertFalse(report['cases'][0]['criterion_pass'])
        self.assertEqual(report['cases'][0]['review_status'], 'flagged')

    def test_expansion_changes_offline_report_without_sending(self):
        with patch('model_services.requests.post') as post:
            report = evaluate(dataset_path=ROOT/'evaluation/challenge_cases.json', source_limit=6)
        self.assertEqual(report['retrieval']['all_evidence_hits'], 14)
        self.assertEqual(report['source_limit'], 6)
        post.assert_not_called()


class RepeatReportTests(unittest.TestCase):
    def report(self, service='a'):
        return {'live_answers': True, 'dataset_sha256': 'data', 'implementation_sha256': 'code',
            'mode': 'keyword', 'source_limit': 6, 'review_conditions': True,
            'cases': [{'id': 'one', 'criterion_pass': False, 'status': 'unverified', 'review_status': 'flagged', 'answer_seconds': 1.2}],
            'service': {'id': service, 'model': 'model', 'config_fingerprint': service},
            'summary': {'call_count': 2}}

    def test_repeated_summary_distinguishes_interception_from_task_success(self):
        from evaluation.repeat import summarize
        text = summarize([self.report(), self.report(), self.report('b')])
        self.assertIn('0/2', text)
        self.assertIn('被拦截', text)
        self.assertIn('不代表任务已完成', text)

    def test_repeated_summary_rejects_mixed_code_or_send_settings(self):
        from evaluation.repeat import summarize
        for key, value in [('source_limit', 3), ('review_conditions', False), ('implementation_sha256', 'changed')]:
            report = self.report()
            report[key] = value
            with self.assertRaises(ValueError):
                summarize([self.report(), report])

    def test_model_comparison_rejects_different_review_or_source_scope(self):
        from test_challenge_evaluation import ChallengeEvaluationTests
        first = ChallengeEvaluationTests().report()
        for key, value in [('source_limit', 6), ('review_conditions', True)]:
            other = ChallengeEvaluationTests().report()
            other['service']['config_fingerprint'] = 'b'
            other[key] = value
            with self.assertRaisesRegex(ValueError, '设置不同'):
                compare_reports(first, other)
