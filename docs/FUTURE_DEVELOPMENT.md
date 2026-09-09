# Future Development

This document describes proposed improvements for the internal-document assistant and synchronization pipeline. The long-term goal is to evolve the system into a reliable, observable assistant that supports multiple data sources and user groups.

## Product and feature improvements

- Add Google Drive, Notion, Confluence, SharePoint, website, PDF, and DOCX sources.
- Classify documents by product, language, version, and owning team.
- Add manual uploads, document version history, restore, duplicate detection, and explicit deletion confirmation.
- Support multi-turn conversations, citations, answer feedback, clarification questions, and concise or technical answer modes.
- Configure schedules per data source and sync selected document groups.
- Add pause, resume, cancel, failure notifications, and dashboard run history.
- Add authentication, roles, audit logs, document-level access control, quotas, and API rate limits.

## Technical development

### Architecture

- Separate the API, synchronization worker, and frontend into independent services.
- Use Redis Queue, Celery, or a managed queue for long-running jobs.
- Move job state from process memory to PostgreSQL or SQLite.
- Use database migrations and API versioning such as `/api/v1/...`.

### Storage and synchronization

- Keep delta synchronization based on content hashes.
- Store checksums, file sizes, source update times, and source IDs in metadata.
- Use transactions or a two-phase approach for upload, indexing, and local-state updates.
- Use object storage for large files and back up data, logs, and the database regularly.
- Define retention policies without deleting data that is still referenced.

### Retrieval and answer quality

- Evaluate hybrid vector and keyword search, metadata filtering, and reranking.
- Maintain benchmark questions with expected answer points.
- Track groundedness, source accuracy, unanswered-question rate, and latency.
- Prefer an explicit “not enough information” response over unsupported guesses.

### Security

- Store secrets in a secret manager instead of production `.env` files.
- Authenticate webhooks and restrict administrative endpoints where appropriate.
- Validate MIME types, file sizes, and file content before processing.
- Defend against prompt injection and keep system instructions separate from document content.
- Redact sensitive data from logs and define audit-log retention.

### Observability and reliability

- Add structured logging with request IDs and job IDs.
- Add health checks for the API, worker, database, and vector store.
- Use metrics and tracing for scraping, uploading, indexing, and answer generation.
- Retry transient errors with backoff and distinguish them from data errors.
- Make jobs idempotent so retries do not create duplicate records or files.
- Test backups and restores and document disaster recovery.

## Suggested roadmap

### Phase 1 — Stabilize the foundation

1. Store job history in a database instead of only JSON files.
2. Complete the dashboard view for job status and per-run errors.
3. Add tests for retries, reruns, missing files, and vector-store failures.
4. Add source citations to answers.
5. Add health checks, structured logs, and data backups.

### Phase 2 — Improve assistant quality

1. Add answer feedback.
2. Build an evaluation set and run regression checks automatically.
3. Add hybrid search, metadata filtering, and reranking when evaluation justifies them.
4. Support multi-turn conversations and multiple languages.
5. Support document versions.

### Phase 3 — Scale the platform

1. Separate the worker from the dashboard.
2. Move jobs to a queue and safely support multiple workers.
3. Add authentication, authorization, and audit logs.
4. Connect multiple external data sources.
5. Adopt managed scheduler, database, and object storage services.

## Development principles

- Prefer well-grounded answers over plausible answers without sources.
- Do not automatically delete data without state tracking, history, and recovery options.
- Every job should be observable, safely retryable, and explainable when it fails.
- Changes to retrieval or prompts should include before-and-after evaluation.
- Keep source data, synchronization state, operational logs, and conversation history separate.
- Start simple, but keep module boundaries clear so components can be replaced later.
