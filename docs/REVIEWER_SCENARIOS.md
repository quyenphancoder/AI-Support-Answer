# Reviewer Scenario Answers

### Scraper fails halfway

The run stops with an error. Files already written remain local, and state is committed only after successful indexing, so the next run can retry safely.

### 5,000 articles change

Delta sync processes only changed files. For that scale, add bounded concurrency, rate-limit backoff, batching, and a persistent queue.

### An article is deleted

The current implementation avoids destructive automatic deletion. A production version would detect missing source IDs and remove them after review or a retention period.

### Preventing hallucinations

File Search is required, the system prompt requires answers from retrieved documents, and the assistant should say when the knowledge base has no answer.

### Vector search versus the whole prompt

Vector search retrieves only relevant chunks, reducing tokens, latency, and cost while scaling beyond the model context window.

### Improving citation accuracy

Store article ID, title, and URL as metadata, render citations from retrieved results, and validate each displayed URL against those results.
