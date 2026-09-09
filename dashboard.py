"""Local document browser and article synchronization."""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from openai import OpenAI
from main import load_local_articles, save_run
from src.uploader import sync_articles
from ask import answer

load_dotenv()
DATA = Path(os.getenv('DATA_DIR', 'data'))
LOGS = Path(os.getenv('LOG_DIR', 'logs'))
SYNC_LOCK = threading.Lock()
JOB_LOCK = threading.Lock()


def load_last_run():
    path = LOGS / 'last-run.json'
    try:
        value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


LAST_RUN = load_last_run()
SYNC_JOB = {
    'operation': None,
    'status': 'idle',
    'message': 'No background sync has run yet.',
    'started_at': None,
    'finished_at': None,
    'result': LAST_RUN.get('result') if LAST_RUN else None,
    'error': LAST_RUN.get('error') if LAST_RUN else None,
}
if LAST_RUN:
    SYNC_JOB.update(status=LAST_RUN.get('status', 'failed'),
                    operation=LAST_RUN.get('operation'),
                    message=LAST_RUN.get('message', 'Last run loaded.'),
                    started_at=LAST_RUN.get('started_at'),
                    finished_at=LAST_RUN.get('finished_at'))


def set_job(**changes):
    with JOB_LOCK:
        SYNC_JOB.update(changes)


def sync_job_status():
    with JOB_LOCK:
        return dict(SYNC_JOB)


def sync_local_article(name):
    root = (DATA / 'articles').resolve()
    path = (root / name).resolve()
    if path.parent != root or path.suffix != '.md' or not path.is_file():
        raise ValueError('Article not found.')
    content = path.read_text(encoding='utf-8')
    url = next((line.removeprefix('Article URL:').strip() for line in content.splitlines()
                if line.startswith('Article URL:')), '')
    if not url:
        raise ValueError('Article is missing its source URL.')
    title = content.splitlines()[0].lstrip('# ').strip() if content else path.stem
    row = dict(id=path.stem, filename=path.name, url=url, title=title,
               sha256=hashlib.sha256(content.encode('utf-8')).hexdigest())
    return sync_articles([row], DATA)


def run_background(operation, task):
    started_at = sync_job_status().get('started_at')
    try:
        result = task()
        finished_at = datetime.now(timezone.utc).isoformat()
        payload = {'status': 'success', 'operation': operation,
                   'message': f'{operation.title()} all completed.',
                   'started_at': started_at, 'finished_at': finished_at,
                   'result': result or {}, 'error': None}
        set_job(**payload)
    except Exception as exc:
        payload = {'status': 'failed', 'operation': operation,
                   'message': f'{operation.title()} all failed.',
                   'started_at': started_at,
                   'finished_at': datetime.now(timezone.utc).isoformat(),
                   'result': None, 'error': str(exc)}
        set_job(**payload)
    finally:
        LOGS.mkdir(parents=True, exist_ok=True)
        save_run(LOGS, payload)
        SYNC_LOCK.release()


def run_sync_all(limit=0):
    def task():
        rows = load_local_articles(DATA, limit)
        result = {'selected': len(rows)}
        result.update(sync_articles(rows, DATA))
        return result
    run_background('sync', task)


def run_scrape_all(limit=0):
    def task():
        from src.scraper import scrape
        return {'scraped': len(scrape(DATA, limit))}
    run_background('scrape', task)


def start_sync_all(limit=0):
    if not SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError('Another sync is already running.')
    set_job(status='running', operation='sync', message='Sync all is running in the background.',
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None, result=None, error=None)
    threading.Thread(target=run_sync_all, args=(limit,), daemon=True).start()
    return sync_job_status()


def start_scrape_all(limit=0):
    if not SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError('Another job is already running.')
    set_job(status='running', operation='scrape', message='Scrape all is running in the background.',
            started_at=datetime.now(timezone.utc).isoformat(), finished_at=None, result=None, error=None)
    threading.Thread(target=run_scrape_all, args=(limit,), daemon=True).start()
    return sync_job_status()


def state():
    path = DATA / 'upload-state.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def local_articles():
    saved = state().get('articles', {})
    articles = []
    # Enumerate actual files, not the latest scrape's manifest.
    for path in sorted((DATA / 'articles').glob('*.md')):
        content = path.read_text(encoding='utf-8')
        previous = saved.get(path.stem)
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        sync = 'Not uploaded' if not previous else ('Indexed locally' if previous['sha256'] == digest else 'Changed locally')
        articles.append(dict(filename=path.name, title=content.splitlines()[0].lstrip('# ').strip() if content else path.stem,
                             bytes=path.stat().st_size, sync=sync))
    return {'articles': articles}


def store_files():
    saved = state()
    store_id = os.getenv('OPENAI_VECTOR_STORE_ID')
    key = os.getenv('OPENAI_API_KEY') or os.getenv('API_KEY')
    if not store_id:
        return {'files': [], 'message': 'No vector store configured. Run a sync first.'}
    if not key:
        return {'files': [], 'store_id': store_id, 'message': 'Set OPENAI_API_KEY and recreate the container.'}
    names = {v['file_id']: f'{k}.md' for k, v in saved.get('articles', {}).items()}
    titles = {v['file_id']: v.get('title') for v in saved.get('articles', {}).values()}
    local_titles = {article['filename']: article['title'] for article in local_articles()['articles']}
    with OpenAI(api_key=key, timeout=20, max_retries=1) as client:
        store = client.vector_stores.retrieve(store_id)
        rows = []
        # SDK iteration follows pagination; records come from the live store.
        for item in client.vector_stores.files.list(vector_store_id=store_id, limit=100):
            filename = names.get(item.id)
            if not filename:
                filename = client.files.retrieve(item.id).filename
            title = titles.get(item.id) or local_titles.get(filename) or filename
            rows.append(dict(id=item.id, filename=filename, title=title, status=item.status, bytes=item.usage_bytes))
    return {'store_id': store_id, 'name': store.name, 'files': rows}


class Handler(BaseHTTPRequestHandler):
    def json_response(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ('/api/sync', '/api/sync-all', '/api/scrape-all', '/api/chat'):
            self.json_response(404, {'error': 'Not found.'})
            return
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            self.json_response(403, {'error': 'Origin not allowed.'})
            return
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.json_response(415, {'error': 'Expected JSON.'})
            return
        if self.path in ('/api/sync-all', '/api/scrape-all'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                payload = json.loads(self.rfile.read(length)) if length else {}
                limit = payload.get('limit', 0) if isinstance(payload, dict) else 0
                if not isinstance(limit, int) or limit < 0:
                    raise ValueError('Limit must be a positive number, or 0 for all.')
                starter = start_scrape_all if self.path == '/api/scrape-all' else start_sync_all
                self.json_response(202, starter(limit))
            except RuntimeError as exc:
                self.json_response(409, {'error': str(exc)})
            except ValueError as exc:
                self.json_response(400, {'error': str(exc)})
            except Exception:
                self.json_response(502, {'error': 'Unable to start background job.'})
            return
        if self.path == '/api/chat':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16000:
                    raise ValueError('Question is too long.')
                payload = json.loads(self.rfile.read(length))
                question = payload.get('question') if isinstance(payload, dict) else None
                if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
                    raise ValueError('Enter a question of 1–2000 characters.')
                response = answer(question.strip())
                self.json_response(200, {'answer': response.output_text or 'No answer was returned. Please try another question.'})
            except ValueError as exc:
                self.json_response(400, {'error': str(exc)})
            except Exception:
                self.json_response(502, {'error': 'Unable to answer. Check model access, API credits, and vector store configuration, then retry.'})
            return
        if not SYNC_LOCK.acquire(blocking=False):
            self.json_response(409, {'error': 'Another article is syncing. Please wait.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Invalid request size.')
            payload = json.loads(self.rfile.read(length))
            name = payload.get('filename') if isinstance(payload, dict) else None
            if not isinstance(name, str) or not name:
                raise ValueError('Select an article.')
            self.json_response(200, sync_local_article(name))
        except ValueError as exc:
            self.json_response(400, {'error': str(exc)})
        except Exception:
            self.json_response(502, {'error': 'Sync failed. Check API access and indexing status, then retry.'})
        finally:
            SYNC_LOCK.release()

    def do_GET(self):
        route = urlparse(self.path)
        try:
            assets = {
                '/': ('dashboard.html', 'text/html; charset=utf-8'),
                '/dashboard.js': ('dashboard.js', 'text/javascript; charset=utf-8'),
            }
            if route.path in assets:
                filename, content_type = assets[route.path]
                body = (Path(__file__).parent / filename).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
            else:
                if route.path == '/api/local':
                    payload = local_articles()
                elif route.path == '/api/store':
                    payload = store_files()
                elif route.path == '/api/sync-status':
                    payload = sync_job_status()
                elif route.path == '/api/article':
                    name = parse_qs(route.query).get('name', [''])[0]
                    root = (DATA / 'articles').resolve()
                    path = (root / name).resolve()
                    if path.parent != root or path.suffix != '.md' or not path.is_file():
                        self.send_error(404)
                        return
                    payload = {'content': path.read_text(encoding='utf-8')}
                else:
                    self.send_error(404)
                    return
                body = json.dumps(payload).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            # Do not send SDK exceptions or credential details to the browser.
            body = json.dumps({'error': 'Unable to load data. Check API access, store ID, connection, and local JSON files.'}).encode()
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)


if __name__ == '__main__':
    print('Document browser listening on port 8080', flush=True)
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
