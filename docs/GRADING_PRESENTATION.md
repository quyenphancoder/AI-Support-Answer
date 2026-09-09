# Amber Atlas — Grading & Demo Guide

## 1. Product overview

Amber Atlas is a small RAG support assistant for OptiSigns. It downloads public help-center articles, converts them to clean Markdown, indexes the documents in an existing OpenAI Vector Store, and answers support questions with OpenAI File Search.

The project is Docker-first: the web dashboard and the scheduled worker run as separate Compose services.

## 2. Business flow

```text
OptiSigns Help Center
        ↓
Scraper + HTML cleanup
        ↓
Markdown files in data/articles/
        ↓
SHA-256 delta detection
        ↓
OpenAI Vector Store
        ↓
File Search + model response
        ↓
Dashboard chat answer
```

The scraper writes one Markdown file per article. During upload, the app compares the current SHA-256 hash with `data/upload-state.json`:

- `added`: article has no previous upload state.
- `updated`: the article hash changed; the new version is indexed and the old version is removed.
- `skipped`: the hash is unchanged.

## 3. Architecture

| Component | Responsibility |
| --- | --- |
| `src/scraper.py` | Zendesk API pagination, filtering, HTML cleanup and Markdown conversion |
| `src/uploader.py` | OpenAI Files API, Vector Store indexing, chunking and delta sync |
| `main.py` | One-shot scrape, upload-only, or full pipeline CLI |
| `ask.py` | Responses API + File Search question answering |
| `dashboard.py` | Local article browser, live Vector Store list and background job API |
| `deploy/daily.py` | Cron scheduler and timestamped job logs |
| `compose.yaml` | Dashboard and daily worker services |

## 4. Grading coverage

### Scrape & clean quality

Implemented:

- Uses the OptiSigns Help Center API with pagination.
- Skips drafts, duplicate IDs and empty article bodies.
- Removes `script`, `style`, `nav` and `noscript` elements.
- Preserves headings, links, code blocks and the source URL.
- Writes UTF-8 Markdown files under `data/articles/`.
- Retries temporary HTTP failures and uses request timeouts.

Demo command:

```sh
python main.py --scrape-only --limit 30
```

### API-based vector-store upload

Implemented:

- Uses the OpenAI Files API and Vector Store Files API.
- Uses an existing Vector Store ID from `OPENAI_VECTOR_STORE_ID`.
- Uses static chunking: maximum 800 tokens with 400-token overlap.
- Uploads only new or changed articles.
- Polls indexing until completion and cleans up replaced files.
- Persists hashes and file IDs in `data/upload-state.json`.
- Logs `added`, `updated`, `skipped`, `files_embedded` and `chunks_estimated`.

The final chunk count is not exposed by the OpenAI indexing response. `chunks_estimated` is therefore a local estimate, clearly labelled as such.

Demo command:

```sh
python main.py --upload-only --limit 30
```

### Daily job deployment & logs

Implemented:

- The `daily` Compose service runs continuously in the background.
- `deploy/daily.py --schedule` installs a cron entry.
- Default schedule: 02:00 UTC / 09:00 Vietnam time.
- A file lock prevents overlapping daily runs.
- Each run writes a timestamped `.log` and `.json` artefact.
- The latest result is written to `logs/last-run.json`.

Demo commands:

```powershell
docker compose up -d daily
docker compose ps
docker compose logs -f daily
```

### Code clarity + README

Implemented:

- Small modules with single responsibilities.
- Shared background-job handling for scrape and sync.
- Clear environment configuration.
- Docker-only setup with no local virtual environment requirement.
- README covers setup, local commands, daily logs and demo screenshot placeholder.

### Bonus tests

The test suite covers:

- Markdown structure and HTML cleanup.
- New, unchanged and updated article handling.
- Failed indexing and timeout recovery.
- Upload-only mode and argument validation.
- Dashboard chat and background sync endpoints.

Run:

```sh
python -m unittest discover -s tests -v
```

## 5. Presentation demo script

1. Show `.env` with the API key, model and manually created Vector Store ID.
2. Run `docker compose up -d --build`.
3. Open `http://localhost:8080`.
4. Click **Scrape all** and show the background status and local article list.
5. Click **Sync all** and show `added`, `updated` and `skipped` counts.
6. Open a local Markdown article and compare it with the Vector Store file list.
7. Ask: `How do I add a YouTube video?`
8. Show the answer and explain that File Search retrieves relevant chunks before the model responds.
9. Show daily service status and `logs/last-run.json`.

## 6. Key files and artefacts

```text
data/articles/*.md       Scraped local knowledge base
data/upload-state.json   Delta-sync hashes and OpenAI file IDs
logs/last-run.json       Latest pipeline result
logs/<timestamp>.log     Daily run output
logs/<timestamp>.json    Daily run summary
```

## 7. Closing statement

Amber Atlas demonstrates the complete knowledge pipeline: collect support content, clean it, index it through an AI API, detect changes efficiently, schedule updates, and expose the result through a simple support chat interface.
