# betterme-backend

Backend for a multi-mode RAG advisory assistant with strict mode isolation:
- `relationship`
- `coaching`
- `personal_growth`

## Implemented
- FastAPI chat endpoint with session context (`POST /chat`)
- Qdrant vector storage with isolated collections per mode
- Real OpenAI embeddings (`text-embedding-3-small` by default)
- Document ingestion pipeline for `TXT/PDF/DOCX` with chunking and indexing (`POST /ingest`)
- Long-term memory storage as structured summaries + embeddings (mode-specific)
- Safety rails for self-harm and violence/abuse requests
- Basic admin status endpoint (`GET /admin/status`)
- Metrics endpoint (`GET /admin/metrics`) with token/cost and moderation logs

## Project Structure
```text
app/
  core/
    qdrant_db.py      # Qdrant client + collection setup
    chunking.py
    embeddings.py
    llm.py
    prompts.py
    safety.py
    telemetry.py
  routes/
    admin.py
    chat.py
    ingestion.py
  services/
    ingestion.py
    rag.py
  main.py
seed_cloud_vectors.py
```

## Environment Variables
```bash
AUTH_JWT_SECRET=                # for HS* tokens (or set AUTH_JWT_PUBLIC_KEY for RS*)
AUTH_JWT_PUBLIC_KEY=            # optional PEM public key for RS256/RS512
AUTH_JWT_ALGORITHMS=HS256       # comma-separated, e.g. RS256
AUTH_JWT_AUDIENCE=              # optional
AUTH_JWT_ISSUER=                # optional

OPENAI_API_KEY=                  # set in secrets manager
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_ROUTE=production          # production | testing
OPENAI_TEST_API_KEY=             # optional (used when OPENAI_ROUTE=testing)
OPENAI_TEST_MODEL=gpt-4o-mini
OPENAI_TEST_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_BASE_URL=
OPENAI_TEST_BASE_URL=

EMBEDDING_MAX_TOKENS=8000
EMBEDDING_RETRY_LIMIT=3
LLM_MAX_TOKENS=2000
LLM_RETRY_LIMIT=3

QDRANT_URL=                      # required
QDRANT_API_KEY=                  # required
EMBEDDING_DIMENSION=1536

CHUNK_TOKENS=800
CHUNK_OVERLAP_TOKENS=120
```

## Install & Run
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## APIs
- `POST /chat`
  - header: `Authorization: Bearer <jwt>`
  - body: `{ "mode": "coaching", "message": "...", "session_id": "required", "relationship_id": "optional" }`
  - note: `relationship_id` is required when `mode` is `mediation` / `relationship_medication`
- `POST /ingest` (multipart form-data)
  - header: `Authorization: Bearer <jwt>`
  - fields: `mode`, `session_id` (optional), `source` (optional), `file` (`.txt/.pdf/.docx`)
- `GET /admin/status`
  - returns ingestion/usage counters, collection counts, and recent error logs
- `GET /admin/metrics`
  - returns metrics (tokens, cost), error logs, moderation logs

## Seed Knowledge Base
Place files in:
```text
knowledge_base/relationship/
knowledge_base/coaching/
knowledge_base/personal_growth/
```
Then run:
```bash
python seed_cloud_vectors.py
```
