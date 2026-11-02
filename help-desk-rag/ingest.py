"""PART 1 - document processing: load -> chunk -> embed -> store in SQLite.

Re-runnable: unchanged files are skipped, changed files are replaced and
files removed from disk are deleted from the index.

    python help-desk-rag/ingest.py [--rebuild] [--path DIR] [--include-untrusted]
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml
from llama_index.core import Document
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.core.schema import TextNode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from sqlite_store import SQLiteVectorStore  # noqa: E402

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
# Metadata kept out of the text that gets embedded (it would only add noise).
NOISY_KEYS = ["file_path", "source_id", "version", "effective_date", "owner",
              "classification", "doc_type"]


def parse_markdown(path: Path, base: Path) -> tuple[str, Document]:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    match = FRONT_MATTER.match(raw)
    if match:
        meta = yaml.safe_load(match.group(1)) or {}
        raw = raw[match.end():]
    rel = path.relative_to(base).as_posix()
    meta = {k: str(v) for k, v in meta.items()}
    meta["file_path"] = rel
    meta["doc_type"] = "known-issue" if "known-issues" in path.parts else "policy"
    meta.setdefault("title", path.stem)
    meta.setdefault("source_id", path.stem)
    doc = Document(
        text=raw,
        doc_id=rel,
        metadata=meta,
        excluded_embed_metadata_keys=NOISY_KEYS,
        excluded_llm_metadata_keys=NOISY_KEYS,
    )
    return hashlib.sha256(path.read_bytes()).hexdigest(), doc


def load_documents(base: Path, include_untrusted: bool = False):
    docs = []
    for path in sorted(base.rglob("*.md")):
        if not include_untrusted and set(path.relative_to(base).parts) & config.UNTRUSTED_DIRS:
            continue
        docs.append(parse_markdown(path, base))
    return docs


def chunk(doc: Document) -> list[TextNode]:
    """Split by Markdown heading first, then cap oversized sections."""
    sections = MarkdownNodeParser().get_nodes_from_documents([doc])
    splitter = SentenceSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )
    nodes = [n for n in splitter.get_nodes_from_documents(sections) if n.text.strip()]
    for node in nodes:
        headers = sorted(k for k in node.metadata if k.startswith("Header_"))
        node.metadata["section"] = " > ".join(node.metadata.pop(k) for k in headers[1:]) or (
            node.metadata.get(headers[0], "") if headers else ""
        )
        for k in headers:
            node.metadata.pop(k, None)
    return nodes


def embed_nodes(nodes: list[TextNode], embed_model: BaseEmbedding) -> None:
    embeddings = embed_model.get_text_embedding_batch(
        [n.get_content(metadata_mode="embed") for n in nodes]
    )
    for node, emb in zip(nodes, embeddings):
        node.embedding = emb


def ingest_document(
    store: SQLiteVectorStore, embed_model: BaseEmbedding, file_hash: str, doc: Document
) -> dict:
    """Run one document through chunk -> embed -> store and return a trace of each step."""
    nodes = chunk(doc)
    embed_nodes(nodes, embed_model)
    store.add(nodes)
    store.record_document(
        doc.doc_id, doc.metadata.get("source_id", ""),
        doc.metadata.get("version", ""), file_hash,
    )
    return {
        "doc_id": doc.doc_id,
        "metadata": dict(doc.metadata),
        "characters": len(doc.text),
        "chunks": [
            {
                "node_id": n.node_id,
                "section": n.metadata.get("section", ""),
                "chars": len(n.text),
                "text": n.text,
                "embedded_text": n.get_content(metadata_mode="embed"),
                "embedding_dim": len(n.embedding),
                "embedding_preview": [round(x, 4) for x in n.embedding[:8]],
            }
            for n in nodes
        ],
    }


def check_embed_model(store: SQLiteVectorStore, embed_model: BaseEmbedding) -> None:
    model_name = getattr(embed_model, "model_name", type(embed_model).__name__)
    previous = store.get_meta("embed_model")
    if previous and previous != model_name:
        raise ValueError(
            f"Index was built with '{previous}', current model is '{model_name}'. "
            "Rebuild the index."
        )
    store.set_meta("embed_model", model_name)


def ingest_file(store: SQLiteVectorStore, embed_model: BaseEmbedding, path: Path) -> dict:
    """Ingest one file (e.g. an upload), replacing any earlier version of it."""
    check_embed_model(store, embed_model)
    file_hash, doc = parse_markdown(path, path.parent)
    store.delete(doc.doc_id)
    return ingest_document(store, embed_model, file_hash, doc)


def ingest(
    store: SQLiteVectorStore,
    embed_model: BaseEmbedding,
    base: Path = config.DOCS_DIR,
    rebuild: bool = False,
    include_untrusted: bool = False,
) -> dict:
    if rebuild:
        store.clear()
    try:
        check_embed_model(store, embed_model)
    except ValueError as exc:
        raise SystemExit(f"{exc} Re-run with --rebuild.") from exc

    known = store.get_document_hashes()
    found = load_documents(base, include_untrusted)
    current_ids = {d.doc_id for _, d in found}
    stats = {"added": 0, "updated": 0, "skipped": 0, "removed": 0, "chunks": 0}

    for stale in set(known) - current_ids:
        store.delete(stale)
        stats["removed"] += 1

    for file_hash, doc in found:
        if known.get(doc.doc_id) == file_hash:
            stats["skipped"] += 1
            continue
        if doc.doc_id in known:
            store.delete(doc.doc_id)
            stats["updated"] += 1
        else:
            stats["added"] += 1
        stats["chunks"] += len(ingest_document(store, embed_model, file_hash, doc)["chunks"])
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", type=Path, default=config.DOCS_DIR)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--include-untrusted", action="store_true")
    args = parser.parse_args()

    from llama_index.embeddings.openai import OpenAIEmbedding

    store = SQLiteVectorStore(config.DB_PATH)
    stats = ingest(
        store,
        OpenAIEmbedding(model=config.EMBED_MODEL),
        args.path,
        args.rebuild,
        args.include_untrusted,
    )
    print(f"Ingest done: {stats}; total chunks in DB: {store.count()} ({config.DB_PATH})")


if __name__ == "__main__":
    main()
