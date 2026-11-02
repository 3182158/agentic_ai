"""A LlamaIndex vector store backed by a single SQLite file.

Vectors are stored as float32 BLOBs next to the chunk text and metadata;
similarity search is brute-force cosine in NumPy (fine for a small corpus).
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
from llama_index.core.schema import BaseNode, TextNode
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    VectorStoreQuery,
    VectorStoreQueryResult,
)
from llama_index.core.vector_stores.utils import (
    metadata_dict_to_node,
    node_to_metadata_dict,
)
from llama_index.core.bridge.pydantic import PrivateAttr

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    node_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    source_id TEXT,
    version TEXT,
    file_hash TEXT NOT NULL,
    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


class SQLiteVectorStore(BasePydanticVectorStore):
    stores_text: bool = True
    is_embedding_query: bool = True
    db_path: str

    _conn: sqlite3.Connection = PrivateAttr()

    def __init__(self, db_path: str | Path, **kwargs: Any) -> None:
        super().__init__(db_path=str(db_path), **kwargs)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA)

    @classmethod
    def class_name(cls) -> str:
        return "SQLiteVectorStore"

    @property
    def client(self) -> sqlite3.Connection:
        return self._conn

    # ---- write ----
    def add(self, nodes: List[BaseNode], **kwargs: Any) -> List[str]:
        rows = []
        for node in nodes:
            emb = np.asarray(node.get_embedding(), dtype=np.float32)
            meta = node_to_metadata_dict(node, remove_text=True, flat_metadata=False)
            rows.append(
                (
                    node.node_id,
                    node.ref_doc_id or node.node_id,
                    node.get_content(),
                    json.dumps(meta),
                    emb.tobytes(),
                )
            )
        with self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?)", rows
            )
        return [n.node_id for n in nodes]

    def delete(self, ref_doc_id: str, **kwargs: Any) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (ref_doc_id,))
            self._conn.execute("DELETE FROM documents WHERE doc_id = ?", (ref_doc_id,))

    def clear(self) -> None:
        with self._conn:
            for table in ("chunks", "documents", "meta"):
                self._conn.execute(f"DELETE FROM {table}")

    # ---- document / meta bookkeeping (used by ingestion) ----
    def get_document_hashes(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT doc_id, file_hash FROM documents")
        return dict(rows.fetchall())

    def record_document(
        self, doc_id: str, source_id: str, version: str, file_hash: str
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO documents (doc_id, source_id, version, file_hash)"
                " VALUES (?,?,?,?)",
                (doc_id, source_id, version, file_hash),
            )

    def get_meta(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def list_documents(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT d.doc_id, d.source_id, d.version, d.ingested_at, COUNT(c.node_id)"
            " FROM documents d LEFT JOIN chunks c ON c.doc_id = d.doc_id"
            " GROUP BY d.doc_id ORDER BY d.doc_id"
        ).fetchall()
        keys = ("doc_id", "source_id", "version", "ingested_at", "chunks")
        return [dict(zip(keys, r)) for r in rows]

    def list_chunks(self, doc_id: str | None = None) -> list[dict]:
        sql = "SELECT node_id, doc_id, text, metadata_json, embedding FROM chunks"
        rows = self._conn.execute(
            sql + (" WHERE doc_id = ?" if doc_id else "") + " ORDER BY rowid",
            (doc_id,) if doc_id else (),
        ).fetchall()
        return [
            {
                "node_id": r[0],
                "doc_id": r[1],
                "text": r[2],
                "section": json.loads(r[3]).get("section", ""),
                "embedding_dim": len(r[4]) // 4,
                "embedding_preview": [
                    round(float(x), 4) for x in np.frombuffer(r[4], dtype=np.float32)[:8]
                ],
            }
            for r in rows
        ]

    # ---- read ----
    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        if query.query_embedding is None:
            raise ValueError("query_embedding is required")
        rows = self._conn.execute(
            "SELECT node_id, text, metadata_json, embedding FROM chunks"
        ).fetchall()
        if query.filters:
            wanted = {f.key: f.value for f in query.filters.filters}
            rows = [
                r
                for r in rows
                if all(json.loads(r[2]).get(k) == v for k, v in wanted.items())
            ]
        if not rows:
            return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])

        matrix = np.vstack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
        q = np.asarray(query.query_embedding, dtype=np.float32)
        denom = np.linalg.norm(matrix, axis=1) * np.linalg.norm(q)
        scores = (matrix @ q) / np.where(denom == 0, 1, denom)

        top = np.argsort(-scores)[: query.similarity_top_k]
        nodes: List[TextNode] = []
        for i in top:
            node_id, text, meta_json, _ = rows[i]
            meta = json.loads(meta_json)
            node = metadata_dict_to_node(meta)
            node.set_content(text)
            nodes.append(node)
        return VectorStoreQueryResult(
            nodes=nodes,
            similarities=[float(scores[i]) for i in top],
            ids=[rows[i][0] for i in top],
        )
