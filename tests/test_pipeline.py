import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from openai import NotFoundError

from src.scraper import to_markdown
from src.uploader import sync_articles


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'articles').mkdir()
        (self.root / 'articles/1.md').write_text('# Example', encoding='utf-8')
        self.rows = [dict(id='1', filename='1.md', sha256='first', url='https://example.com/1')]
        self.client = MagicMock()
        self.client.files.create.side_effect = [SimpleNamespace(id='file_first'), SimpleNamespace(id='file_second')]
        response = httpx.Response(404, request=httpx.Request('GET', 'https://example.com'))
        self.client.vector_stores.files.retrieve.side_effect = NotFoundError('missing', response=response, body=None)
        self.client.vector_stores.files.create_and_poll.return_value.status = 'completed'
        environment = patch.dict('os.environ', {'OPENAI_VECTOR_STORE_ID': 'vs_demo'})
        environment.start()
        self.addCleanup(environment.stop)

    def test_new_unchanged_updated(self):
        self.assertEqual(sync_articles(self.rows, self.root, self.client)['added'], 1)
        self.assertEqual(sync_articles(self.rows, self.root, self.client)['skipped'], 1)
        self.assertEqual(self.client.files.create.call_count, 1)
        self.rows[0]['sha256'] = 'second'
        self.assertEqual(sync_articles(self.rows, self.root, self.client)['updated'], 1)
        self.client.files.delete.assert_called_once_with('file_first')
        state = json.loads((self.root / 'upload-state.json').read_text())
        self.assertEqual(state['articles']['1']['file_id'], 'file_second')

    def test_failed_indexing_does_not_commit_hash(self):
        self.client.vector_stores.files.create_and_poll.return_value.status = 'failed'
        with self.assertRaisesRegex(RuntimeError, 'Indexing failed'):
            sync_articles(self.rows, self.root, self.client)
        state = json.loads((self.root / 'upload-state.json').read_text())
        self.assertEqual(state['articles'], {})
        self.client.vector_stores.files.create_and_poll.return_value.status = 'completed'
        self.assertEqual(sync_articles(self.rows, self.root, self.client)['added'], 1)

    def test_timeout_resumes_existing_upload(self):
        self.client.vector_stores.files.create_and_poll.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            sync_articles(self.rows, self.root, self.client)
        self.client.vector_stores.files.retrieve.side_effect = None
        self.client.vector_stores.files.retrieve.return_value.status = 'completed'
        self.assertEqual(sync_articles(self.rows, self.root, self.client)['added'], 1)
        self.assertEqual(self.client.files.create.call_count, 1)

    def test_markdown_preserves_structure(self):
        result = to_markdown(dict(title='Example', html_url='https://example.com/1',
            body='<nav>Navigation</nav><h2>Steps</h2><a href="/help">Help</a><pre><code>print(1)</code></pre>'))
        for expected in ['## Steps', '[Help](/help)', '```', 'Article URL: https://example.com/1']:
            self.assertIn(expected, result)
        self.assertNotIn('Navigation', result)


if __name__ == '__main__':
    unittest.main()
