# Reviewer Q&A — Amber Atlas

Use these answers as speaking notes. Keep the explanation simple and connect every design choice to the product flow.

## Product and architecture

### What does the app do?

It builds a small RAG support assistant for OptiSigns. The app scrapes public help articles, converts them to Markdown, uploads new or changed documents to an OpenAI Vector Store, and answers questions with File Search.

### What is the end-to-end flow?

`OptiSigns API → scraper → Markdown files → SHA-256 comparison → Vector Store → File Search → model answer`.

### Why is the project split into modules?

The scraper, uploader, question answering, dashboard, and scheduler have separate responsibilities. This makes each part easier to test, replace, and debug.

## Scraping and Markdown

### Where does the data come from?

The scraper reads the public OptiSigns Zendesk Help Center API. It follows pagination until it reaches the requested limit or the final page.

### What cleaning is performed?

It removes `script`, `style`, `nav`, and `noscript` elements, skips drafts and empty bodies, and converts the remaining HTML into Markdown while preserving headings, links, code blocks, and the article URL.

### Does `--limit 30` select random articles?

No. It selects the first 30 valid articles returned by the API order. The limit is useful for a small demo.

### Why store Markdown locally?

Markdown is readable, easy to inspect in the dashboard, portable between AI providers, and gives the uploader a stable file to hash and upload.

## Delta sync

### Why use SHA-256?

The app calculates a SHA-256 hash from the final Markdown content. If the hash is unchanged, the article content is unchanged from the last successful upload.

### How are `added`, `updated`, and `skipped` calculated?

No previous state means `added`. A previous hash that differs means `updated`. A matching hash means `skipped`.

### Why keep `upload-state.json`?

It stores the previous hash and OpenAI `file_id` for each article. The hash enables delta detection, and the file ID lets the app remove the replaced version after the new version is indexed.

### What happens if indexing fails?

The new hash is not committed as successful state. The pending upload remains recoverable or is cleaned up, and the next run can retry without falsely marking the article as synced.

### Why is Vector Store ID in `.env`?

The assignment uses an existing Vector Store created manually. The app validates and uses `OPENAI_VECTOR_STORE_ID`; it does not create a store automatically.

## Vector Store and RAG

### What is chunking?

Chunking divides a long document into smaller searchable sections. The app requests static chunks of up to 800 tokens with 400-token overlap so context is preserved across boundaries.

### Does the app split files itself?

No. It uploads one Markdown file and asks OpenAI to perform the configured chunking and indexing server-side.

### What happens when a user asks a question?

The Responses API receives the question and a File Search tool configured with the Vector Store ID. OpenAI retrieves relevant chunks, then the model writes an answer using that retrieved context.

### Why is `chunks_estimated` not exact?

OpenAI does not expose the final generated chunk count in the indexing response. The app logs a local estimate and clearly labels it as an estimate instead of claiming it is an API-confirmed count.

## Dashboard and background jobs

### Why are Scrape all and Sync all separate?

Scrape all refreshes local Markdown from OptiSigns. Sync all uploads local files to OpenAI. Separating them lets a user inspect or edit local content before paying for an upload.

### Does Sync all use the search filter?

No. It syncs every Markdown file in `data/articles/`. The filter only changes what is displayed. Delta detection still skips unchanged files.

### Why use a background thread?

Scraping and indexing can take time. The API returns immediately with HTTP 202, the worker runs in the background, and the UI polls `/api/sync-status` so the browser remains responsive.

### Can two jobs run at the same time?

No. A shared lock rejects a second scrape or sync while one job is active. This prevents conflicting state updates and duplicate uploads.

## Daily job and operations

### How does the daily job work?

The `daily` container stays running, installs a cron schedule, and calls `main.py` at the configured UTC time. `main.py` performs a fresh scrape followed by delta upload.

### What if the computer is off at the scheduled time?

The local cron job misses that run; it does not replay it automatically. The user can run the daily command manually after restarting Docker.

### Where are results recorded?

The latest pipeline result is in `logs/last-run.json`. Daily runs also create timestamped `.log` and `.json` files. Docker stdout can be viewed with `docker compose logs -f daily`.

### Why is `upload-state.json` in `data/` and logs in `logs/`?

`data/` contains application state required for future runs. `logs/` contains historical run output and summaries. Keeping them separate prevents operational logs from being confused with sync state.

## Docker and testing

### Why use Docker instead of a local virtual environment?

Docker gives the reviewer the same Python version, dependencies, dashboard service, and daily worker without requiring local Python setup.

### How can the image run once and exit?

The image defaults to `python main.py`, so `docker run ... amber-atlas main.py` performs one pipeline run and exits with code 0 on success. Compose overrides the command for the long-running dashboard and daily services.

### How is the code tested?

The tests cover Markdown cleanup, upload delta behavior, failures, timeouts, upload-only mode, argument validation, chat, and background sync. Run them with:

```sh
python -m unittest discover -s tests -v
```

## Honest limitations

The scraper depends on the public Help Center API and its response order. Daily scheduling is local to Docker Desktop, not a cloud scheduler. The final number of OpenAI-generated chunks is not available through the current API response, so the project reports an estimate.
