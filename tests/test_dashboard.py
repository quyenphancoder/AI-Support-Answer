import hashlib
import tempfile
import unittest
import threading
import json
import time
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import dashboard


class DashboardTests(unittest.TestCase):
    def setUp(self):
        dashboard.set_job(status='idle', message='No background sync has run yet.',
                          started_at=None, finished_at=None, result=None, error=None)

    def test_chat_endpoint_returns_answer(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), dashboard.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.object(dashboard, 'answer', return_value=SimpleNamespace(output_text='Answer from documents.')) as ask:
                request = Request(f'http://127.0.0.1:{server.server_port}/api/chat',
                                  data=json.dumps({'question': 'How do I add a YouTube video?'}).encode(),
                                  headers={'Content-Type': 'application/json'})
                with urlopen(request) as response:
                    self.assertEqual(json.load(response)['answer'], 'Answer from documents.')
                ask.assert_called_once_with('How do I add a YouTube video?')
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_sync_reads_selected_file_without_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'articles').mkdir()
            content = '# Example\n\nArticle URL: https://example.com/article\n'
            (root / 'articles/123.md').write_text(content, encoding='utf-8')
            with patch.object(dashboard, 'DATA', root), patch.object(dashboard, 'sync_articles') as sync:
                dashboard.sync_local_article('123.md')
                rows, data = sync.call_args.args
                self.assertEqual(data, root)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['id'], '123')
                self.assertEqual(rows[0]['sha256'], hashlib.sha256(content.encode()).hexdigest())
                with self.assertRaises(ValueError):
                    dashboard.sync_local_article('../secret.md')
                self.assertEqual(sync.call_count, 1)

    def test_sync_all_runs_in_background(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'articles').mkdir()
            (root / 'articles/123.md').write_text(
                '# Example\n\nArticle URL: https://example.com/article\n',
                encoding='utf-8',
            )
            with patch.object(dashboard, 'DATA', root), patch.object(dashboard, 'sync_articles', return_value={'added': 1, 'updated': 0, 'skipped': 0}):
                started = dashboard.start_sync_all()
                self.assertEqual(started['status'], 'running')
                for _ in range(20):
                    status = dashboard.sync_job_status()
                    if status['status'] != 'running':
                        break
                    time.sleep(0.05)
                self.assertEqual(status['status'], 'success')
                self.assertEqual(status['result']['selected'], 1)
                self.assertEqual(status['result']['added'], 1)
