"""Central settings for the help-desk RAG (paths, models, chunking, retrieval)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DOCS_DIR = ROOT / "mock-data" / "documents"
# Poisoned prompt-injection fixture; only ingested with --include-untrusted.
UNTRUSTED_DIRS = {"security-training"}
DB_PATH = Path(os.getenv("RAG_DB_PATH", ROOT / ".data" / "rag" / "rag.sqlite3"))

EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Sections larger than CHUNK_SIZE tokens are split further, with overlap so
# a sentence cut at the boundary still appears whole in one chunk.
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

TOP_K = 4
# Cosine similarity below this is treated as "not relevant" -> "not covered".
SIMILARITY_CUTOFF = float(os.getenv("RAG_SIMILARITY_CUTOFF", "0.30"))

NOT_COVERED = (
    "I couldn't find this in the policy or known-issue documents. "
    "I can raise a ticket or you can contact HR/IT for help."
)
