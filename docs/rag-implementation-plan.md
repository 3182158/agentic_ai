# RAG Implementation Plan (LlamaIndex + SQLite)

Location: `help-desk-rag/` (currently an empty `rag.py`).
Corpus: `mock-data/documents/{policies,known-issues}` (the `security-training/` poisoned fixture is excluded by default).

## 1. How RAG works (behaviour)

```
            PART 1: INGESTION (offline, re-runnable)
 Markdown docs ─► Load ─► Clean/parse ─► Chunk ─► Embed ─► SQLite vector DB
 (+front matter)          (metadata)     (nodes)  (vectors)  (text+vector+metadata)

            PART 2: QUERY (online, per question)
 Question ─► Embed ─► Top-k similarity search ─► (score cutoff) ─► Prompt(context + question) ─► LLM ─► Answer + citations
                                                       └─ nothing relevant ─► "Not covered in documents" (no LLM guess)
```

- **Why RAG:** the LLM doesn't know Acme's policies. We fetch the relevant text at question time and force the model to answer only from it.
- **Embeddings:** text → vector; similar meaning → close vectors. Question and chunks are embedded with the *same* model.
- **Chunking:** whole docs are too coarse; tiny chunks lose context. Split by Markdown heading first (each `## N. Section` is one policy rule), then cap size.
- **Grounding:** if the best score is below a threshold, answer "not covered" and offer to raise a ticket / contact HR (query P9).
- **Most RAG failures are retrieval failures** → the query CLI must be able to show retrieved chunks and scores.

## 2. Design decisions

| Topic | Decision |
|---|---|
| Framework | `llama-index-core` (already in `pyproject.toml`) |
| Embeddings | `OpenAIEmbedding` `text-embedding-3-small` (key in `.env`) |
| LLM | `OpenAI` using `OPENAI_MODEL` (default `gpt-4o-mini`), temperature 0 |
| Vector DB | **SQLite file** `.data/rag/rag.sqlite3` |
| Chunking | `MarkdownNodeParser` (by heading) → `SentenceSplitter(chunk_size=512, overlap=64)` for oversized sections |
| Metadata | `source_id, title, version, effective_date, owner, doc_type (policy/known-issue), file_path, section heading` |
| Top-k | 4, similarity cutoff ~0.3 (tune with eval questions) |

### SQLite vector store (key point)
LlamaIndex has no built-in SQLite vector store (the current `.data/llamaindex/*.json` is the default in-memory/JSON store). Two options:

1. **Recommended: `sqlite-vec` extension + small custom `BasePydanticVectorStore`** (`add`, `delete`, `query`). Tables:
   - `chunks(node_id PK, doc_id, text, metadata_json, content_hash)`
   - `vec_chunks` (sqlite-vec virtual table, `float[1536]`, rowid → chunks)
   - `documents(doc_id PK, source_id, version, file_hash, ingested_at)` for versioning / incremental re-ingest.
2. Fallback (no extension): store vectors as BLOB and do brute-force cosine in NumPy. Fine for ~10 docs; same interface.

## 3. File layout

```
help-desk-rag/
  config.py          # paths, model names, chunk/top-k/threshold, env loading
  sqlite_store.py    # SQLiteVectorStore (LlamaIndex vector store implementation)
  ingest.py          # PART 1: load → chunk → embed → store  (CLI)
  query.py           # PART 2: retrieve → generate → cite    (CLI)
  rag.py             # stable interface: RagService.search(q) / .answer(q) for LangGraph later
  tests/             # pytest
```

## 4. Part 1 — Document processing (`ingest.py`)

1. **Load:** `SimpleDirectoryReader(recursive=True, required_exts=[".md"])`; exclude `security-training/` (flag `--include-untrusted`).
2. **Parse front matter** (`source_id`, `version`, …) into node metadata; strip it from the text.
3. **Chunk:** as in the table above; attach section heading to metadata and to chunk text (heading prefix improves retrieval).
4. **Embed:** batch embed nodes.
5. **Store:** upsert into SQLite; skip unchanged files via `file_hash`; delete stale chunks when a file changed/removed (idempotent, re-runnable).
6. **Report:** docs, chunks, tokens estimate; `--rebuild` drops and recreates.

CLI: `python help-desk-rag/ingest.py [--rebuild] [--path mock-data/documents]`

## 5. Part 2 — Query (`query.py`)

1. Load `VectorStoreIndex.from_vector_store(SQLiteVectorStore, embed_model)`.
2. `VectorIndexRetriever(similarity_top_k=4)` + `SimilarityPostprocessor(cutoff)`.
3. If no nodes survive → return fixed "not covered" response (no LLM call).
4. Else `get_response_synthesizer` with a strict prompt: *answer only from context; cite `[source_id §section]`; say so if insufficient*.
5. Output: answer, sources (title, section, version, score), optional `--show-chunks` debug view.
6. Optional filter: `--doc-type policy|known-issue`.

CLI: `python help-desk-rag/query.py "Can I carry forward unused leave?" [--show-chunks]`

## 6. Implementation steps

1. Add deps: `sqlite-vec`, `numpy` (via `uv add`); add `OPENAI_EMBED_MODEL` to `.env.example`.
2. `config.py` + `sqlite_store.py` with unit tests (add/query/delete using fake vectors, no API).
3. `ingest.py` with front-matter parsing and hash-based incremental logic; test chunk output on `leave-and-time-off.md`.
4. `query.py` with grounding threshold + citations.
5. `rag.py` facade (`RagService`) returning structured results (`answer`, `sources`, `grounded: bool`).
6. Evaluate with question set (below); tune chunk size/top-k/cutoff.
7. Update README with run instructions; later wire `RagService` as a tool for the LangGraph policy agent.

## 7. Acceptance / test questions

| Question | Expected |
|---|---|
| "Can I carry forward unused leave?" | Up to 5 days, expire 31 March; cites `policy-leave-001` §2 |
| "How long before must I submit leave?" | 5 working days / 4 weeks for >5 days |
| "My VPN keeps disconnecting" | Steps from the VPN known-issue doc |
| "Policy on personal devices abroad?" | "Not covered" response (grounding works) |
| Poisoned fixture text | Never retrieved unless `--include-untrusted`; retrieved text treated as data, not instructions |

Tests: store unit tests, ingest idempotency (run twice → no duplicate chunks), query grounding with a stubbed embed model.

## 8. Risks / notes

- Existing `.data/llamaindex/` JSON index is obsolete once SQLite is used; keep `.data/` git-ignored.
- Changing the embedding model requires `--rebuild` (store the model name in a metadata table and refuse mismatches).
- `.venv` is Python 3.12 (`requires-python >=3.12`); the system `python3` is 3.11 — use `uv run` / `.venv/bin/python`.
