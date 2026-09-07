import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class UploadOnlyTests(unittest.TestCase):
    def test_reads_current_files_with_limit_without_scraping(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'articles').mkdir()
            content = '# Current title\nArticle URL: https://example.com/1\nEdited locally\n'
            for name in ['2.md', '1.md']:
                (root / 'articles' / name).write_text(content, encoding='utf-8')
            (root / 'manifest.json').write_text('[]')
            with patch.dict('os.environ', {'DATA_DIR': folder, 'LOG_DIR': str(root / 'logs')}), patch('sys.argv', ['main.py', '--upload-only', '--limit', '1']), patch.object(main, 'scrape') as scrape, patch.object(main, 'sync_articles', return_value={'added': 1}) as sync:
                self.assertEqual(main.main(), 0)
                scrape.assert_not_called()
                rows = sync.call_args.args[0]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['filename'], '1.md')
                self.assertEqual(rows[0]['sha256'], hashlib.sha256(content.encode()).hexdigest())
            self.assertEqual(len(main.load_local_articles(root)), 2)
            self.assertEqual((root / 'manifest.json').read_text(), '[]')
            self.assertEqual(json.loads((root / 'logs' / 'last-run.json').read_text())['mode'], 'upload')

    def test_empty_or_invalid_files_fail_before_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, 'No local Markdown'):
                main.load_local_articles(root)
            (root / 'articles').mkdir()
            (root / 'articles/1.md').write_text('# No source')
            with self.assertRaisesRegex(ValueError, 'missing Article URL'):
                main.load_local_articles(root)

    def test_modes_are_exclusive(self):
        with patch('sys.argv', ['main.py', '--upload-only', '--scrape-only']):
            with self.assertRaises(SystemExit) as error:
                main.main()
            self.assertEqual(error.exception.code, 2)
