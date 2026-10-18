import os
from pathlib import Path
import unittest
from unittest.mock import patch

from conversation import Turn
from documents import text_document
from grounding import AnswerResult
from model_services import ModelSession
from rag_core import answer_document, retrieve_document
from test_model_services import response, service


class DataControlsTests(unittest.TestCase):
    def test_block_overrides_existing_consent_and_rejects_new_consent(self):
        session = ModelSession()
        session.approve(service(), 'doc')
        session.set_document_blocked('doc', True)
        with patch('model_services.requests.post') as post:
            for phase in ['rewrite', 'answer']:
                with self.assertRaisesRegex(RuntimeError, '禁止'):
                    session.call(service(), 'doc', 'secret', phase)
            with self.assertRaisesRegex(RuntimeError, '禁止'):
                session.approve(service(), 'doc')
        post.assert_not_called()
        self.assertEqual(session.records, [])

    def test_unblock_needs_fresh_consent_and_other_documents_are_separate(self):
        session = ModelSession()
        session.set_document_blocked('restricted', True)
        session.approve(service(), 'other')
        self.assertTrue(session.allowed(service(), 'other'))
        session.set_document_blocked('restricted', False)
        self.assertFalse(session.allowed(service(), 'restricted'))
        session.approve(service(), 'restricted')
        self.assertTrue(session.allowed(service(), 'restricted'))

    def test_history_policy_change_invalidates_consent_and_blocks_rewrite(self):
        session = ModelSession()
        session.approve(service(), 'doc')
        session.set_history_allowed(False)
        self.assertFalse(session.allowed(service(), 'doc'))
        session.approve(service(), 'doc')
        with patch('model_services.requests.post') as post:
            with self.assertRaisesRegex(RuntimeError, '关闭历史'):
                session.call(service(), 'doc', 'private history', 'rewrite')
        post.assert_not_called()
        session.set_history_allowed(True)
        self.assertFalse(session.allowed(service(), 'doc'))

    def test_original_passages_require_no_model_or_credentials(self):
        doc = text_document('正式员工每年有十天年假。', 'policy.txt')
        with patch('rag_core.call_llm') as model, patch('model_services.requests.post') as post:
            sources = retrieve_document(doc, '年假')
        model.assert_not_called()
        post.assert_not_called()
        self.assertEqual(sources[0].filename, 'policy.txt')
        self.assertIn('十天', sources[0].text)

    def test_ui_block_still_searches_and_unblock_does_not_restore_consent(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ, {'TENCENT_API_KEY': 'test', 'TENCENT_API_BASE_URL': 'https://example.invalid/v1', 'MODEL_SERVICES_CONFIG': ''}), patch('model_services.requests.post', return_value=response()) as post:
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
            app.toggle[0].set_value(True).run()
            next(b for b in app.button if b.label == '确认接收方并允许当前文档问答').click().run()
            next(t for t in app.toggle if t.label == '禁止发送给模型服务').set_value(True).run()
            self.assertTrue(app.chat_input[0].disabled)
            next(t for t in app.text_input if t.label == '输入文档中的关键词').set_value('年假')
            next(b for b in app.button if b.label == '查找原文').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('年假' in value.value for value in app.markdown))
            post.assert_not_called()
            next(t for t in app.toggle if t.label == '禁止发送给模型服务').set_value(False).run()
            self.assertTrue(app.chat_input[0].disabled)

    def test_ui_history_disabled_sends_only_independent_question(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ, {'TENCENT_API_KEY': 'test', 'TENCENT_API_BASE_URL': 'https://example.invalid/v1', 'MODEL_SERVICES_CONFIG': ''}), patch('model_services.requests.post', return_value=response()) as post:
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
            app.toggle[0].set_value(True).run()
            next(b for b in app.button if b.label == '确认接收方并允许当前文档问答').click().run()
            app.chat_input[0].set_value('正式员工年假几天？').run()
            next(c for c in app.checkbox if c.label == '允许发送历史问答以理解追问').uncheck().run()
            self.assertTrue(app.chat_input[0].disabled)
            next(b for b in app.button if b.label == '确认接收方并允许当前文档问答').click().run()
            app.chat_input[0].set_value('试用期员工年假几天？').run()
            self.assertFalse(app.exception)
            self.assertEqual(post.call_count, 2)
            self.assertNotIn('最新问题改写', post.call_args.kwargs['json']['messages'][0]['content'])
            self.assertEqual([r['phase'] for r in app.session_state.model_session.records], ['answer', 'answer'])
            self.assertFalse(app.session_state.conversation.turns[-1].history_allowed)
            self.assertEqual(len(app.session_state.conversation.turns), 2)
            self.assertIn('历史问答发送：关闭', app.session_state.conversation.export_markdown())


if __name__ == '__main__':
    unittest.main()
