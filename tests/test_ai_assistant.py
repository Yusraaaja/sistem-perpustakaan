# -*- coding: utf-8 -*-
"""Regression tests for AI Book Assistant, Smart Search, and related security."""
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('GEMINI_API_KEY', 'test-gemini-key-not-real')

import app as library_app


class FakeHTTPResponse:
    def __init__(self, payload, status=200):
        self._payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def gemini_payload(text, finish_reason='STOP', extra_parts=None):
    parts = extra_parts[:] if extra_parts else []
    if text is not None:
        parts.append({'text': text})
    return {
        'candidates': [
            {
                'content': {'parts': parts, 'role': 'model'},
                'finishReason': finish_reason
            }
        ]
    }


class GeminiHelperTests(unittest.TestCase):
    def test_extract_skips_thought_parts_and_joins_text(self):
        candidate = {
            'finishReason': 'STOP',
            'content': {
                'parts': [
                    {'thought': True, 'text': 'internal chain of thought'},
                    {'text': 'Rekomendasi: Atomic Habits [ID: 6]. '},
                    {'text': 'Alasan: membantu membangun kebiasaan membaca.'}
                ]
            }
        }
        text, reason = library_app._extract_gemini_candidate_text(candidate)
        self.assertEqual(reason, 'STOP')
        self.assertIn('Atomic Habits', text)
        self.assertIn('Alasan:', text)
        self.assertNotIn('internal chain of thought', text)

    def test_payload_uses_raised_token_limit_and_disables_thinking(self):
        payload = library_app._build_gemini_payload('sys', 'user', 4096, True)
        self.assertEqual(payload['generationConfig']['maxOutputTokens'], 4096)
        self.assertGreaterEqual(payload['generationConfig']['maxOutputTokens'], 2048)
        self.assertEqual(payload['generationConfig']['thinkingConfig']['thinkingBudget'], 0)


class CallGeminiApiTests(unittest.TestCase):
    def setUp(self):
        os.environ['GEMINI_API_KEY'] = 'test-gemini-key-not-real'

    def test_complete_response_is_success(self):
        full = (
            'Saya merekomendasikan Atomic Habits [ID: 6].\n'
            'Penulis: James Clear\n'
            'Alasan: buku ini membahas pembentukan kebiasaan kecil yang konsisten.'
        )
        with patch('urllib.request.urlopen', return_value=FakeHTTPResponse(gemini_payload(full, 'STOP'))):
            ok, text = library_app.call_gemini_api('sys', 'rekomendasi kebiasaan')
        self.assertTrue(ok)
        self.assertIn('Alasan:', text)
        self.assertTrue(text.endswith('konsisten.'))

    def test_max_tokens_retries_once_then_returns_complete_text(self):
        truncated = '**Atomic Habits [ID: 6]\n* **Penulis:** James Clear\n* **Alasan'
        complete = truncated + ': membantu siswa membangun kebiasaan belajar yang berkelanjutan.'
        responses = [
            FakeHTTPResponse(gemini_payload(truncated, 'MAX_TOKENS')),
            FakeHTTPResponse(gemini_payload(complete, 'STOP')),
        ]
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(json.loads(req.data.decode('utf-8')))
            return responses.pop(0)

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            ok, text = library_app.call_gemini_api('sys', 'rekomendasi')

        self.assertTrue(ok)
        self.assertIn('berkelanjutan', text)
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0]['generationConfig']['maxOutputTokens'], 4096)
        self.assertEqual(captured[1]['generationConfig']['maxOutputTokens'], 8192)

    def test_max_tokens_twice_is_not_treated_as_success(self):
        truncated = '**Atomic Habits [ID: 6]\n* **Alasan'
        responses = [
            FakeHTTPResponse(gemini_payload(truncated, 'MAX_TOKENS')),
            FakeHTTPResponse(gemini_payload(truncated, 'MAX_TOKENS')),
        ]

        def fake_urlopen(req, timeout=None):
            return responses.pop(0)

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            ok, err = library_app.call_gemini_api('sys', 'rekomendasi')

        self.assertFalse(ok)
        self.assertEqual(err.error_code, 'ai_output_truncated')
        self.assertNotIn('Alasan', str(err))  # truncated body is not returned as the user-facing success text
        self.assertIn('terpotong', err.message)

    def test_empty_candidates_is_error(self):
        with patch('urllib.request.urlopen', return_value=FakeHTTPResponse({'candidates': []})):
            ok, err = library_app.call_gemini_api('sys', 'halo')
        self.assertFalse(ok)
        self.assertEqual(err.error_code, 'ai_upstream_error')

    def test_malformed_json_is_error(self):
        with patch('urllib.request.urlopen', return_value=FakeHTTPResponse(b'NOT-JSON')):
            ok, err = library_app.call_gemini_api('sys', 'halo')
        self.assertFalse(ok)
        self.assertEqual(err.error_code, 'ai_upstream_error')

    def test_http_error_does_not_leak_upstream_message(self):
        err_body = json.dumps({
            'error': {
                'message': 'API key test-gemini-key-not-real is invalid',
                'status': 'INVALID_ARGUMENT'
            }
        }).encode('utf-8')
        http_err = urllib.error.HTTPError(
            'https://generativelanguage.googleapis.com/fake',
            400,
            'Bad Request',
            hdrs=None,
            fp=io.BytesIO(err_body)
        )
        with patch('urllib.request.urlopen', side_effect=http_err):
            ok, err = library_app.call_gemini_api('sys', 'halo')
        self.assertFalse(ok)
        blob = json.dumps({'message': err.message, 'error_code': err.error_code})
        self.assertNotIn('test-gemini-key-not-real', blob)
        self.assertNotIn('API key', err.message)


class AiChatEndpointTests(unittest.TestCase):
    def setUp(self):
        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()
        os.environ['GEMINI_API_KEY'] = 'test-gemini-key-not-real'

    def _csrf(self):
        with self.client.session_transaction() as sess:
            sess['_csrf_token'] = 'csrf-test-token'
        return {'X-CSRFToken': 'csrf-test-token'}

    def test_complete_ai_chat_verifies_book_ids(self):
        answer = (
            'Saya merekomendasikan Atomic Habits [ID: 6] dan buku fiktif [ID: 99999].\n'
            'Alasan: Atomic Habits membantu membentuk kebiasaan membaca harian.'
        )
        with patch('urllib.request.urlopen', return_value=FakeHTTPResponse(gemini_payload(answer, 'STOP'))):
            res = self.client.post(
                '/api/ai_chat',
                headers={**self._csrf(), 'Content-Type': 'application/json'},
                data=json.dumps({'message': 'rekomendasi kebiasaan', 'csrf_token': 'csrf-test-token'})
            )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('Alasan:', data['answer'])
        ids = [b['id'] for b in data['books']]
        self.assertIn(6, ids)
        self.assertNotIn(99999, ids)
        self.assertNotIn('test-gemini-key-not-real', res.get_data(as_text=True))

    def test_ai_chat_truncated_after_retry_is_error_json(self):
        truncated = '**Atomic Habits [ID: 6]\n* **Alasan'
        responses = [
            FakeHTTPResponse(gemini_payload(truncated, 'MAX_TOKENS')),
            FakeHTTPResponse(gemini_payload(truncated, 'MAX_TOKENS')),
        ]

        def fake_urlopen(req, timeout=None):
            return responses.pop(0)

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            res = self.client.post(
                '/api/ai_chat',
                headers={**self._csrf(), 'Content-Type': 'application/json'},
                data=json.dumps({'message': 'rekomendasi', 'csrf_token': 'csrf-test-token'})
            )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['error_code'], 'ai_output_truncated')
        self.assertNotIn('test-gemini-key-not-real', res.get_data(as_text=True))

    def test_ai_chat_rejects_csrf_missing(self):
        res = self.client.post(
            '/api/ai_chat',
            headers={'Content-Type': 'application/json'},
            data=json.dumps({'message': 'halo'})
        )
        self.assertEqual(res.status_code, 400)

    def test_ai_chat_empty_message(self):
        res = self.client.post(
            '/api/ai_chat',
            headers={**self._csrf(), 'Content-Type': 'application/json'},
            data=json.dumps({'message': '   ', 'csrf_token': 'csrf-test-token'})
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data['status'], 'error')


class SmartSearchRegressionTests(unittest.TestCase):
    def setUp(self):
        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

    def test_search_suggestions_match_title(self):
        res = self.client.get('/api/search_suggestions?q=Atomic')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertTrue(any('Atomic' in (item.get('judul') or '') for item in data))
        blob = res.get_data(as_text=True)
        self.assertNotIn('password', blob.lower())
        self.assertNotIn('GEMINI_API_KEY', blob)
        for item in data:
            self.assertIn('id', item)
            self.assertIn('judul', item)
            self.assertNotIn('sinopsis', item)

    def test_search_suggestions_empty_query(self):
        res = self.client.get('/api/search_suggestions?q=')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

    def test_retrieve_relevant_books_returns_catalog_ids(self):
        books = library_app.retrieve_relevant_books('Atomic Habits')
        self.assertTrue(books)
        self.assertTrue(all(isinstance(b['id'], int) for b in books))
        self.assertTrue(any(b['id'] == 6 for b in books))


class FrontendContractTests(unittest.TestCase):
    def test_sendquery_stops_spinner_in_finally(self):
        html_path = os.path.join(ROOT, 'templates', 'layout.html')
        with open(html_path, encoding='utf-8') as fh:
            html = fh.read()
        self.assertIn('async function sendQuery', html)
        self.assertIn('function setBusy', html)
        self.assertIn('setBusy(false)', html)
        self.assertIn("btnSpinner.classList.add('d-none')", html)
        self.assertIn('SraX AI Agent', html)
        self.assertIn('function renderAiMarkdown', html)
        self.assertIn('function typewriteAnswer', html)
        self.assertIn('aria-label="Buka SraX AI Agent"', html)
        self.assertNotIn('marked.js', html)
        self.assertNotIn('GEMINI_API_KEY', html)

    def test_index_no_longer_hosts_inline_ai_panel(self):
        html_path = os.path.join(ROOT, 'templates', 'index.html')
        with open(html_path, encoding='utf-8') as fh:
            html = fh.read()
        self.assertNotIn('id="aiChatForm"', html)
        self.assertNotIn('async function sendQuery', html)

    def test_home_page_includes_srax_widget_without_secrets(self):
        library_app.app.config['TESTING'] = True
        client = library_app.app.test_client()
        res = client.get('/')
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('SraX AI Agent', body)
        self.assertIn('sraxAiFab', body)
        self.assertNotIn('GEMINI_API_KEY', body)
        self.assertNotIn('generativelanguage.googleapis.com', body)


if __name__ == '__main__':
    unittest.main()
