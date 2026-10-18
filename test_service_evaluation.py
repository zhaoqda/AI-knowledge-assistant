import os
import unittest
from unittest.mock import patch

from evaluation.run import evaluate, render_report
from model_services import ModelSession
from test_model_services import response, service


class ServiceEvaluationTests(unittest.TestCase):
    def test_live_evaluation_requires_explicit_authorization_before_setup(self):
        with patch('evaluation.run.load_services') as config, patch('model_services.requests.post') as post:
            with self.assertRaisesRegex(ValueError, '允许发送'):
                evaluate(answers=True, service_id='a')
            with self.assertRaisesRegex(ValueError, '指定'):
                evaluate(answers=True, allow_model_send=True)
        config.assert_not_called()
        post.assert_not_called()

    def test_unknown_or_unconfigured_service_never_sends(self):
        with patch('evaluation.run.load_services', return_value=[service()]), patch.dict(os.environ, {'TEST_SERVICE_KEY': ''}), patch('model_services.requests.post') as post:
            for selected in ['unknown', 'a']:
                with self.assertRaises(ValueError):
                    evaluate(answers=True, service_id=selected, allow_model_send=True)
        post.assert_not_called()

    def test_retrieval_only_does_not_even_load_model_config(self):
        with patch('evaluation.run.load_services') as config, patch('model_services.requests.post') as post:
            report = evaluate(limit=3)
        config.assert_not_called()
        post.assert_not_called()
        self.assertNotIn('calls', report)
        self.assertEqual(len(report['dataset_sha256']), 64)
        with self.assertRaises(ValueError):
            evaluate(service_id='a')

    def test_selected_service_and_calls_are_recorded_without_credentials(self):
        raw = '{"answerable":true,"claims":[{"text":"正式员工每年十天年假","source_id":1,"quote":"正式员工每年享有十天带薪年假。"}]}'
        reply = response(raw)
        reply.json.return_value['usage'] = {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}
        for config in [service(), service('b', 'https://b.invalid/v1', 'model-b')]:
            with patch('evaluation.run.load_services', return_value=[config]), patch.dict(os.environ, {'TEST_SERVICE_KEY': 'secret-key'}), patch('model_services.requests.post', return_value=reply) as post:
                report = evaluate(answers=True, limit=1, service_id=config.id, allow_model_send=True)
            self.assertEqual(post.call_args.args[0], config.base_url + '/chat/completions')
            self.assertEqual(report['service']['model'], config.model)
            self.assertEqual(report['summary']['criterion_passed'], 1)
            self.assertEqual(report['cases'][0]['citation_check'], 'passed')
            self.assertEqual(report['cases'][0]['call_ids'], [report['calls'][0]['call_id']])
            self.assertEqual(report['summary']['reported_tokens']['total_tokens'], 120)
            self.assertGreaterEqual(report['calls'][0]['elapsed_seconds'], 0)
            self.assertNotIn('secret-key', str(report))

    def test_fabricated_citation_and_service_error_are_not_valid_refusals(self):
        for reply, expected in [(response('{"answerable":true,"claims":[{"text":"年假十天","source_id":99,"quote":"正式员工每年享有十天带薪年假。"}]}'), 'unverified'), (RuntimeError('private server response'), 'error')]:
            with patch('evaluation.run.load_services', return_value=[service()]), patch.dict(os.environ, {'TEST_SERVICE_KEY': 'test'}), patch('model_services.requests.post', side_effect=[reply]) as post:
                report = evaluate(answers=True, limit=1, service_id='a', allow_model_send=True)
            self.assertEqual(report['cases'][0]['status'], expected)
            self.assertEqual(report['summary']['criterion_passed'], 0)
            self.assertEqual(post.call_count, 1)
            self.assertNotIn('private server response', str(report))

    def test_usage_does_not_accept_strings_negative_counts_or_boolean_values(self):
        session = ModelSession()
        session.approve(service(), 'doc')
        reply = response()
        reply.json.return_value['usage'] = {'prompt_tokens': '100', 'completion_tokens': -1, 'total_tokens': True, 'secret': 'not recorded'}
        with patch.dict(os.environ, {'TEST_SERVICE_KEY': 'test'}), patch('model_services.requests.post', return_value=reply):
            session.call(service(), 'doc', 'private prompt', 'answer')
        self.assertNotIn('usage', session.records[0])
        self.assertNotIn('private prompt', session.export())
        self.assertNotIn('not recorded', session.export())

    def test_readable_report_does_not_turn_missing_usage_into_zero(self):
        with patch('evaluation.run.load_services', return_value=[service()]), patch.dict(os.environ, {'TEST_SERVICE_KEY': 'test'}), patch('model_services.requests.post', return_value=response()):
            report = evaluate(answers=True, limit=1, service_id='a', allow_model_send=True)
        self.assertIsNone(report['summary']['reported_tokens']['total_tokens'])
        self.assertEqual(report['summary']['token_reporting_coverage']['total_tokens'], 0)
        markdown = render_report(report)
        self.assertIn('总计 Token：未提供', markdown)
        self.assertIn('覆盖 0/1', markdown)
        self.assertIn('不等于完整语义正确性', markdown)
        self.assertIn('未运行回答', render_report(evaluate(limit=1)))

    def test_followup_records_setup_rewrite_and_answer_calls(self):
        from grounding import AnswerResult
        def fake_answer(document, query, retriever=None, history=(), model_call=None):
            if history:
                model_call('private history', 'rewrite', ())
            model_call('private document', 'answer', ('chunk-id',))
            return AnswerResult('十天', 'answered')
        with patch('evaluation.run.load_services', return_value=[service()]), patch.dict(os.environ, {'TEST_SERVICE_KEY': 'test'}), patch('evaluation.run.answer_document', side_effect=fake_answer), patch('model_services.requests.post', return_value=response()):
            report = evaluate(answers=True, limit=4, service_id='a', allow_model_send=True)
        self.assertEqual(report['cases'][3]['call_count'], 3)
        self.assertEqual([r['phase'] for r in report['calls'][-3:]], ['answer', 'rewrite', 'answer'])
        self.assertNotIn('private history', str(report))


if __name__ == '__main__':
    unittest.main()
