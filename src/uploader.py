"""Synchronize article versions with a persistent OpenAI vector store."""

import json
import logging
import os
from pathlib import Path

from openai import NotFoundError, OpenAI


def estimate_chunks(content: str, max_tokens: int = 800, overlap: int = 400) -> int:
    """Estimate static tokenizer chunks; OpenAI does not expose final chunk counts."""
    token_estimate = max(1, len(content.encode('utf-8')) // 4)
    if token_estimate <= max_tokens:
        return 1
    step = max_tokens - overlap
    return 1 + (token_estimate - max_tokens + step - 1) // step


def save_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
    temporary.replace(path)


def sync_articles(rows: list[dict], data_dir: Path, client=None) -> dict:
    key = os.getenv('OPENAI_API_KEY') or os.getenv('API_KEY')
    if client is None:
        if not key:
            raise ValueError('Set OPENAI_API_KEY or API_KEY before running synchronization.')
        client = OpenAI(api_key=key, timeout=60, max_retries=3)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / 'upload-state.json'
    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    configured = os.getenv('OPENAI_VECTOR_STORE_ID')
    if not configured:
        raise ValueError('Set OPENAI_VECTOR_STORE_ID to an existing vector store before uploading.')
    if configured and state.get('vector_store_id') not in (None, configured):
        raise ValueError('Configured vector store differs from saved state. Use a separate DATA_DIR.')
    store_id = configured
    state.update(vector_store_id=store_id)
    state.setdefault('articles', {})
    state.setdefault('pending', {})
    state.setdefault('cleanup', [])
    save_state(path, state)
    counts = dict(added=0, updated=0, skipped=0, files_embedded=0,
                  chunks_estimated=0, chunks_embedded=None,
                  chunk_count_source='local_estimate; final count not exposed by API',
                  vector_store_id=store_id)

    def cleanup():
        for file_id in list(state['cleanup']):
            try:
                client.vector_stores.files.delete(file_id, vector_store_id=store_id)
            except NotFoundError:
                pass
            # Delete only files created and tracked by this pipeline.
            try:
                client.files.delete(file_id)
            except NotFoundError:
                pass
            state['cleanup'].remove(file_id)
            save_state(path, state)

    cleanup()
    for row in rows:
        article_id = row['id']
        previous = state['articles'].get(article_id)
        if previous and previous['sha256'] == row['sha256']:
            counts['skipped'] += 1
            continue
        pending = state['pending'].get(article_id)
        if pending and pending['sha256'] != row['sha256']:
            state['cleanup'].append(pending['file_id'])
            del state['pending'][article_id]
            save_state(path, state)
            cleanup()
            pending = None
        if pending is None:
            with (data_dir / 'articles' / row['filename']).open('rb') as source:
                uploaded = client.files.create(file=source, purpose='assistants')
            pending = dict(file_id=uploaded.id, sha256=row['sha256'])
            state['pending'][article_id] = pending
            save_state(path, state)
        file_id = pending['file_id']
        try:
            indexed = client.vector_stores.files.retrieve(file_id, vector_store_id=store_id)
        except NotFoundError:
            indexed = client.vector_stores.files.create_and_poll(
                file_id=file_id, vector_store_id=store_id,
                attributes={'article_id': article_id},
                chunking_strategy={'type': 'static', 'static': {
                    'max_chunk_size_tokens': 800, 'chunk_overlap_tokens': 400}},
            )
        if indexed.status == 'in_progress':
            indexed = client.vector_stores.files.poll(file_id, vector_store_id=store_id)
        if indexed.status != 'completed':
            state['cleanup'].append(file_id)
            del state['pending'][article_id]
            save_state(path, state)
            raise RuntimeError(f'Indexing failed for article {article_id}: {indexed.status}')
        state['articles'][article_id] = dict(pending, url=row['url'], title=row.get('title'))
        del state['pending'][article_id]
        if previous:
            state['cleanup'].append(previous['file_id'])
        save_state(path, state)
        counts['updated' if previous else 'added'] += 1
        counts['files_embedded'] += 1
        content = (data_dir / 'articles' / row['filename']).read_text(encoding='utf-8')
        counts['chunks_estimated'] += estimate_chunks(content)
        logging.info('Indexed article %s as %s', article_id, file_id)
        cleanup()
    logging.info(
        'Embedding summary: files=%d, chunks_estimated=%d, chunking=max 800 tokens/400 overlap',
        counts['files_embedded'], counts['chunks_estimated']
    )
    return counts
