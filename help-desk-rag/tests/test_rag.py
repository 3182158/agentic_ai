import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from llama_index.core.base.embeddings.base import BaseEmbedding

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import ingest as ingest_mod  # noqa: E402
from rag import RagService  # noqa: E402
from sqlite_store import SQLiteVectorStore  # noqa: E402

DIM = 512


class HashEmbedding(BaseEmbedding):
    """Offline bag-of-words embedding so tests need no API key."""

    def _embed(self, text: str) -> list[float]:
        vec = np.zeros(DIM)
        for word in re.findall(r"[a-z]+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1
        return vec.tolist()

    def _get_query_embedding(self, query): return self._embed(query)
    def _get_text_embedding(self, text): return self._embed(text)
    async def _aget_query_embedding(self, query): return self._embed(query)


@pytest.fixture
def store(tmp_path):
    return SQLiteVectorStore(tmp_path / "rag.sqlite3")


def test_ingest_is_idempotent(store):
    embed = HashEmbedding()
    first = ingest_mod.ingest(store, embed)
    count = store.count()
    second = ingest_mod.ingest(store, embed)
    assert first["added"] > 0 and count > 0
    assert second["added"] == 0 and second["skipped"] == first["added"]
    assert store.count() == count


def test_untrusted_docs_excluded_by_default(store):
    ingest_mod.ingest(store, HashEmbedding())
    assert "security-training" not in " ".join(store.get_document_hashes())


def test_carry_forward_retrieves_leave_policy(store):
    embed = HashEmbedding()
    ingest_mod.ingest(store, embed)
    service = RagService(store, embed, cutoff=0.1)
    top = service.search("Can I carry forward unused annual leave days?")[0]
    assert top.source_id == "policy-leave-001"
    assert "Carry-forward" in top.section


def test_unrelated_question_is_not_covered(store):
    embed = HashEmbedding()
    ingest_mod.ingest(store, embed)
    result = RagService(store, embed, cutoff=0.9).answer("quantum banana submarine")
    assert not result.grounded and result.answer == config.NOT_COVERED
