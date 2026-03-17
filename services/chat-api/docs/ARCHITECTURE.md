# Backend Architecture & Security Summary

## Secrets & Config
- Secrets come only from the hosting platform’s secrets manager (Railway/Render/AWS/GCP). Code fails fast if `OPENAI_API_KEY` or `QDRANT_API_KEY` is missing.
- No hardcoded secrets in code; `.env` uses blanks/placeholders for local testing only. Do not commit real values.
- If any secret ever needs DB persistence, store encrypted via the platform KMS; app code assumes KMS-managed decryption and never logs decrypted values.

## Data Flow
1. `/ingest` and `/chat` require a Bearer JWT. `user_id` is derived server-side from token claims (`sub`/`uid`/`user_id`).
2. `/ingest` (multipart) accepts `mode`, optional `session_id`, optional `source`, and file (txt/pdf/docx).
3. Text is tokenized (`tiktoken`) and split by token count; embeddings created; chunks upserted into Qdrant with payload: `{user_id, session_id, mode, source, filename, chunk_index, text}`.
4. `/chat` request (with required `session_id`) is moderated first; RAG fetches context filtered by `user_id` (and `session_id` when provided); long-term memory also filtered.
5. LLM call with retries/backoff; token usage and cost logged; reply stored to memory with `user_id` + `session_id`.

## Security Diagram (textual)
- Client -> FastAPI
  - Moderation check (OpenAI Moderation API)
  - Rate limit middleware
  - Business logic
  - Qdrant (vectors) — payload filtered by `user_id`/`session_id`
- Secrets: provisioned only in platform secrets manager; accessed via env; never logged.
- Logs: structured JSON to stdout (can be shipped to centralized logging).
- Metrics: `/admin/metrics` exposes counters, token totals, cost.

## Embedding Lifecycle
- Token-based chunking with `tiktoken`; sizes configurable (`CHUNK_TOKENS`, `CHUNK_OVERLAP_TOKENS`).
- Embeddings via OpenAI (or OpenRouter fallback); retries with exponential backoff; logs model + count.
- Stored in Qdrant with per-user payload isolation.

## Memory Isolation
- Every ingest/search payload includes server-derived `user_id`; queries enforce `user_id` (and `session_id` when supplied).
- No in-memory document text cache is used for retrieval.
- Long-term memory entries saved with `user_id` + `session_id`; retrieval filter matches both.

## Logging & Observability
- Per-request JSON logs: path, status, latency.
- LLM/embedding call logs: model, message count/input count.
- Token usage + rough cost (configurable table) tracked and exposed via `/admin/metrics`.
- Moderation flags logged (recent entries surfaced in admin).

## Moderation & Safety
- OpenAI Moderation API pre-response; flagged content blocked with safe messaging.
- Keyword fallback exists as secondary guard.
- Flags recorded in structured logs for audit.

## Items to configure in secrets manager (no defaults)
- `OPENAI_API_KEY`
- `QDRANT_API_KEY`
- `QDRANT_URL`
- Optional: `OPENAI_BASE_URL`, `OPENROUTER_API_KEY`, etc.
