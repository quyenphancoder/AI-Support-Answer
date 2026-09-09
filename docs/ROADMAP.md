# Amber Atlas — Future Development Roadmap

The current project satisfies the take-home scope. The following improvements would make it more reliable and production-ready.

## 1. Reliability and data quality

### Incremental scraping

Use article `updated_at`, HTTP `Last-Modified`, or conditional requests to avoid downloading unchanged articles. This reduces source API traffic and shortens daily runs.

### Deleted article handling

Detect articles removed or unpublished from OptiSigns and remove their corresponding files from the Vector Store after a review or retention period.

### Better content extraction

Add site-specific selectors and validation for tables, images, embedded videos, and callout blocks. Keep a small fixture set from real articles to catch scraper regressions.

## 2. Sync and operations

### Durable job queue

Replace the in-process background thread with a persistent queue such as Celery, RQ, or a small database-backed worker. Jobs would survive a dashboard restart and could be retried safely.

### Persistent job history

Store job status, counts, errors, and duration in SQLite or PostgreSQL. Add a dashboard page with searchable run history instead of only the latest artefact and Docker logs.

### Exact embedding metrics

If the AI provider exposes indexing metrics in a future API version, record the confirmed chunk count. Until then, continue labelling local chunk counts as estimates.

### Health checks and alerts

Add Docker health checks and notify an operator when a daily run fails, the API is unavailable, or the Vector Store is inaccessible.

## 3. Retrieval and answer quality

### Evaluation set

Create a small set of representative support questions with expected answer points and source URLs. Run it after scraper or prompt changes to measure retrieval quality.

### Better citations

Render article titles and source URLs as structured citations in the chat response. Verify that every citation belongs to a retrieved document.

### Feedback loop

Allow users to mark an answer helpful or unhelpful and store the question, retrieved sources, and feedback for prompt and retrieval improvements.

### Retrieval controls

Expose configurable result count, score threshold, and metadata filters. This can improve precision when the knowledge base grows.

## 4. Security and access

### Authentication

Protect the dashboard with authentication before exposing it outside localhost.

### Secret management

Use Docker secrets or a managed secret store instead of a local `.env` file in shared environments. Rotate API keys without rebuilding the image.

### Request protection

Add rate limiting, CSRF protection, stricter origin handling, and audit logs for sync operations.

## 5. User experience

### Filtered sync

Add a separate `Sync filtered` action that syncs only the articles currently shown by the search filter, with a clear selected count.

### Job progress

Show completed, skipped, failed, and remaining counts while a scrape or sync is running.

### Export and inspection

Allow users to download Markdown, inspect source metadata, and compare the current article with its previous version.

### Responsive and accessible UI

Improve mobile layout, keyboard navigation, focus states, screen-reader labels, and reduced-motion support.

## 6. Deployment and scale

### Cloud scheduler

Move the daily worker to a managed scheduler such as GitHub Actions, Cloud Run Jobs, AWS EventBridge, or another platform appropriate for the deployment environment.

### Object storage

Store Markdown and job artefacts in object storage when multiple workers or environments need shared access.

### Multi-tenant knowledge bases

Support separate Vector Stores, article sources, prompts, and access policies for different customers or teams.

## Suggested order

1. Add scraper fixtures, evaluation questions, and health checks.
2. Add persistent job history and failure alerts.
3. Improve citations and answer feedback.
4. Add authentication and secret management.
5. Move scheduling and storage to managed cloud services when production scale requires it.
