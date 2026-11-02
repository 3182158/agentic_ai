# Help-desk RAG (LlamaIndex + SQLite)

A small, explainable Retrieval-Augmented Generation (RAG) system over the Acme help-desk documents. It has two parts, a CLI chat and a Streamlit app, and both **show the internals** of each step so the behaviour can be demonstrated.

## How RAG works here

```
PART 1 - INGEST (offline, re-runnable)
 file ─► load + parse ─► chunk ─► embed ─► store
         (front matter   (by      (text →   (SQLite: text +
          → metadata)    heading)  vector)   vector + metadata)

PART 2 - QUERY (per question)
 question ─► embed ─► similarity search ─► cutoff ─► prompt (context + question) ─► LLM ─► answer + citations
                       (top_k, cosine)       └─ nothing relevant ─► "not covered" (LLM not called)
```

| Step | What happens | Setting |
|---|---|---|
| Load + parse | Reads `.md`/`.txt`; YAML front matter (`source_id`, `version`, …) becomes metadata | `ingest.py` |
| Chunk | Split by Markdown heading, then oversized sections split with overlap | `CHUNK_SIZE=512`, `CHUNK_OVERLAP=64` |
| Embed | Each chunk (metadata + text) becomes a vector (OpenAI `text-embedding-3-small`) | `OPENAI_EMBED_MODEL` |
| Store | Chunk text, metadata and vector saved in one SQLite file | `.data/rag/rag.sqlite3` |
| Retrieve | The question is embedded with the same model; cosine similarity ranks all chunks | `TOP_K=4` |
| Ground | Chunks scoring below the cutoff are dropped; none left → "not covered", no LLM call | `RAG_SIMILARITY_CUTOFF=0.30` |
| Generate | LLM answers using only the retrieved context and cites `[source_id §section]` | `OPENAI_MODEL` |

The prompt tells the model to treat retrieved text as data, not instructions. The `security-training/` folder (a prompt-injection fixture) is skipped unless you pass `--include-untrusted`.

## Setup

From the repository root:

```bash
uv sync
cp .env.example .env      # then set OPENAI_API_KEY
```

Optional env vars: `OPENAI_MODEL` (default `gpt-4o-mini`), `OPENAI_EMBED_MODEL`, `RAG_SIMILARITY_CUTOFF`, `RAG_DB_PATH`.

## Run

```bash
# Chat CLI (shows the internals; /help lists commands)
uv run python help-desk-rag/cli.py

# Streamlit app (tabs: Ask, Ingest, Index)
uv run streamlit run help-desk-rag/streamlit_app.py

# Batch-ingest the sample documents (mock-data/documents)
uv run python help-desk-rag/ingest.py [--rebuild] [--path DIR] [--include-untrusted]

# One-shot question
uv run python help-desk-rag/rag.py "Can I carry forward unused leave?" [--show-chunks] [--doc-type policy|known-issue]

# Offline tests (fake embeddings, no API key needed)
uv run pytest help-desk-rag/tests
```

### CLI commands

| Command | Purpose |
|---|---|
| `/ingest [path]` | Ingest a file (shows every step) or a folder (default: sample docs) |
| `/rebuild` | Wipe the index and re-ingest the sample docs |
| `/docs`, `/chunks [doc_id]` | List documents / show stored chunks with vector previews |
| `/stats` | Index size and current settings |
| `/topk N`, `/cutoff X` | Tune retrieval live |
| `/trace on\|off` | Show or hide the step-by-step internals |
| anything else | Treated as a question |

### Streamlit app

- **Ask:** chat; each answer has an expander showing the question vector, all scored candidates (kept vs below cutoff) and the exact prompt sent to the LLM.
- **Ingest:** upload `.md`/`.txt` files and see metadata, chunks and vector previews, or ingest the sample docs.
- **Index:** browse stored documents and chunks.
- **Sidebar:** `top_k` and cutoff sliders, internals toggle, wipe index.

## Demo ideas

1. Ingest a file in the app and walk through chunks and vectors.
2. Ask "Can I carry forward unused leave?" → grounded answer citing `policy-leave-001 §2`.
3. Ask something not in the documents (e.g. personal devices abroad) → "not covered", LLM never called.
4. Raise the cutoff or lower `top_k` and watch candidates drop out.

## Files

| File | Role |
|---|---|
| `config.py` | Paths, model names, chunking and retrieval settings |
| `sqlite_store.py` | LlamaIndex vector store on SQLite (vectors as BLOBs, cosine search in NumPy) |
| `ingest.py` | Part 1: load → chunk → embed → store; incremental and re-runnable (file hashes) |
| `rag.py` | Part 2: `RagService` (`retrieve`, `search`, `answer`) with a step trace; one-shot CLI |
| `cli.py` | Chat CLI |
| `streamlit_app.py` | Streamlit UI |
| `tests/` | Offline tests |

## Notes

- Changing the embedding model requires a rebuild (the index records the model used and refuses a mismatch).
- Similarity search is brute-force NumPy, which is fine for a small corpus; swap `SQLiteVectorStore` for `sqlite-vec` or another store if it grows.
- The Streamlit tables are plain Markdown because `st.dataframe` needs `pyarrow`, which conflicts with the NumPy version LlamaIndex requires here.
- `RagService` is the stable interface to call from the LangGraph agent later.
