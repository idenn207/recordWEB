"""Local desktop OAuth helper tests. Google and NAS requests are mocked."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import requests

from tools import youtube_reauth as auth


class YoutubeReauthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'yt_token.json'
        self.output = self.root / 'new.json'
        self.client = {'client_id': 'test-client', 'client_secret': 'test-secret',
                       'refresh_token': 'old', 'token_uri': 'https://oauth2.googleapis.com/token'}
        self.source.write_text(json.dumps(self.client), encoding='utf-8')

    def test_reuses_client_and_forces_google_endpoints(self):
        config = auth.client_config({**self.client, 'token_uri': 'https://evil.test/token'})
        self.assertEqual(config['installed']['client_id'], 'test-client')
        self.assertEqual(config['installed']['token_uri'], 'https://oauth2.googleapis.com/token')
        self.assertNotIn('refresh_token', config['installed'])
        self.assertEqual(auth.client_config({'installed': self.client}), config)

    def test_rejects_web_client_and_missing_credentials(self):
        for bad in ({'web': self.client}, {}, [], {'client_id': 'id', 'client_secret': 5}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                auth.client_config(bad)

    @patch('tools.youtube_reauth.InstalledAppFlow')
    def test_login_uses_loopback_pkce_and_saves_separate_file(self, flow_class):
        flow_class.from_client_config.return_value.run_local_server.return_value = SimpleNamespace(
            refresh_token='new-refresh', granted_scopes=auth.SCOPES)
        auth.reauthenticate(self.source, self.output)
        self.assertEqual(json.loads(self.source.read_text())['refresh_token'], 'old')
        self.assertEqual(json.loads(self.output.read_text()), {**self.client, 'refresh_token': 'new-refresh'})
        factory_kwargs = flow_class.from_client_config.call_args.kwargs
        self.assertTrue(factory_kwargs['autogenerate_code_verifier'])
        call = flow_class.from_client_config.return_value.run_local_server.call_args.kwargs
        self.assertEqual(call['host'], '127.0.0.1')
        self.assertEqual(call['bind_addr'], '127.0.0.1')
        self.assertEqual(call['port'], 0)
        self.assertEqual(call['prompt'], 'consent')
        self.assertEqual(call['timeout_seconds'], 600)

    @patch('tools.youtube_reauth.InstalledAppFlow')
    def test_cancel_does_not_write_output(self, flow_class):
        flow_class.from_client_config.return_value.run_local_server.side_effect = RuntimeError('secret-detail')
        with self.assertRaises(RuntimeError):
            auth.reauthenticate(self.source, self.output)
        self.assertFalse(self.output.exists())

    @patch('tools.youtube_reauth.InstalledAppFlow')
    def test_missing_refresh_token_or_scope_does_not_overwrite_output(self, flow_class):
        self.output.write_text('previous', encoding='utf-8')
        for refresh, scopes in ((None, auth.SCOPES), ('new', ['openid'])):
            flow_class.from_client_config.return_value.run_local_server.return_value = SimpleNamespace(
                refresh_token=refresh, granted_scopes=scopes)
            with self.subTest(refresh=refresh), self.assertRaises(ValueError):
                auth.reauthenticate(self.source, self.output)
            self.assertEqual(self.output.read_text(), 'previous')

    @patch('tools.youtube_reauth.InstalledAppFlow')
    def test_refuses_to_overwrite_source_before_opening_browser(self, flow_class):
        with self.assertRaises(ValueError):
            auth.reauthenticate(self.source, self.source)
        flow_class.from_client_config.assert_not_called()

    @patch('tools.youtube_reauth.submit_to_nas')
    @patch('tools.youtube_reauth.InstalledAppFlow')
    def test_failed_nas_submission_keeps_new_local_file(self, flow_class, submit):
        flow_class.from_client_config.return_value.run_local_server.return_value = SimpleNamespace(
            refresh_token='new', granted_scopes=auth.SCOPES)
        submit.side_effect = OSError('unavailable')
        with self.assertRaises(OSError):
            auth.reauthenticate(self.source, self.output, 'http://192.168.0.10:5080')
        self.assertTrue(self.output.exists())
        submit.assert_called_once_with('http://192.168.0.10:5080', 'new')

    def test_invalid_nas_url_is_rejected(self):
        for url in ('ftp://localhost', 'http://user:pass@localhost', 'http://localhost/path', 'http://localhost?x=1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                auth.nas_endpoint(url)

    @patch('tools.youtube_reauth.urlopen')
    def test_nas_receives_refresh_token_only(self, open_request):
        open_request.return_value.__enter__.return_value.read.return_value = b'{"ok":true}'
        auth.submit_to_nas('http://192.168.0.10:5080', 'new-refresh')
        request = open_request.call_args.args[0]
        self.assertEqual(request.full_url, 'http://192.168.0.10:5080/api/uploads/reauth')
        self.assertEqual(json.loads(request.data), {'refresh_token': 'new-refresh'})

    def test_real_library_loopback_and_pkce_without_google_network(self):
        callbacks = []
        urls = []

        def open_browser(url, **kwargs):
            urls.append(url)
            params = parse_qs(urlsplit(url).query)
            callback = params['redirect_uri'][0] + '?' + urlencode({
                'state': params['state'][0], 'code': 'test-code',
            })

            def visit_callback():
                with urlopen(callback, timeout=5) as response:
                    self.assertEqual(response.status, 200)

            thread = threading.Thread(target=visit_callback)
            callbacks.append(thread)
            thread.start()
            return True

        def google_response(request, **kwargs):
            self.assertEqual(request.url, 'https://oauth2.googleapis.com/token')
            params = parse_qs(request.body)
            self.assertEqual(params['code'], ['test-code'])
            self.assertTrue(params['code_verifier'][0])
            response = requests.Response()
            response.status_code = 200
            response.request = request
            response._content = json.dumps({
                'access_token': 'mock-access', 'refresh_token': 'loopback-refresh',
                'token_type': 'Bearer', 'expires_in': 3600, 'scope': auth.SCOPES[0],
            }).encode()
            return response

        with patch('webbrowser.get') as browser, patch('requests.sessions.Session.send', side_effect=google_response):
            browser.return_value.open.side_effect = open_browser
            auth.reauthenticate(self.source, self.output)
        for thread in callbacks:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(parse_qs(urlsplit(urls[0]).query)['access_type'], ['offline'])
        self.assertEqual(parse_qs(urlsplit(urls[0]).query)['code_challenge_method'], ['S256'])
        self.assertEqual(json.loads(self.output.read_text())['refresh_token'], 'loopback-refresh')

    @patch('tools.youtube_reauth.reauthenticate')
    def test_main_does_not_print_sensitive_exception_details(self, authenticate):
        import contextlib
        import io
        for error in (RuntimeError('secret-must-not-leak'), auth.UserError('안내 문구'), FileNotFoundError(), KeyboardInterrupt()):
            authenticate.side_effect = error
            output = io.StringIO()
            with self.subTest(error=type(error).__name__), contextlib.redirect_stdout(output):
                self.assertEqual(auth.main([]), 1)
                self.assertNotIn('secret-must-not-leak', output.getvalue())
        authenticate.side_effect = None
        with patch('builtins.print'):
            self.assertEqual(auth.main([]), 0)


if __name__ == '__main__':
    unittest.main()
