"""Streamlit app: ingest files and ask questions while seeing RAG internals.

    streamlit run help-desk-rag/streamlit_app.py
"""

import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import ingest as ingest_mod  # noqa: E402
from rag import RagService  # noqa: E402

st.set_page_config(page_title="Help-desk RAG", layout="wide")


@st.cache_resource
def get_service() -> RagService:
    return RagService.from_env()


service = get_service()

with st.sidebar:
    st.header("Retrieval settings")
    service.top_k = st.slider("top_k (chunks retrieved)", 1, 10, service.top_k)
    service.cutoff = st.slider("similarity cutoff", 0.0, 1.0, service.cutoff, 0.05)
    show_trace = st.toggle("Show internals", value=True)
    st.divider()
    st.metric("Documents", len(service.store.list_documents()))
    st.metric("Chunks", service.store.count())
    st.caption(f"DB: {config.DB_PATH}\n\nEmbeddings: {config.EMBED_MODEL}\n\nLLM: {config.LLM_MODEL}")
    if st.button("Wipe index"):
        service.store.clear()
        st.session_state.pop("messages", None)
        st.rerun()

st.title("Help-desk RAG")
tab_chat, tab_ingest, tab_index = st.tabs(["💬 Ask", "📥 Ingest", "🗄️ Index"])


def md_table(rows: list[dict]) -> None:
    """Markdown table (st.dataframe needs pyarrow, which conflicts with this env's NumPy)."""
    if not rows:
        st.info("Nothing to show yet.")
        return
    clean = lambda v: str(v).replace("|", "\\|").replace("\n", " ")[:90]
    head = "| " + " | ".join(rows[0]) + " |\n|" + "---|" * len(rows[0]) + "\n"
    st.markdown(head + "\n".join("| " + " | ".join(clean(v) for v in r.values()) + " |" for r in rows))


def render_ingest_trace(trace: dict) -> None:
    st.markdown(f"**1-2. Load + parse** `{trace['doc_id']}` ({trace['characters']} chars)")
    st.json(trace["metadata"], expanded=False)
    st.markdown(f"**3. Chunk → 4. Embed** — {len(trace['chunks'])} chunks")
    md_table(
        [
            {"#": i, "section": c["section"], "chars": c["chars"],
             "vector dim": c["embedding_dim"], "vector[:8]": str(c["embedding_preview"]),
             "text": c["text"]}
            for i, c in enumerate(trace["chunks"], 1)
        ],
    )
    with st.expander("Exact text that was embedded (metadata + chunk)"):
        st.code(trace["chunks"][0]["embedded_text"] if trace["chunks"] else "")
    st.markdown("**5. Store** — chunks and vectors written to SQLite")


def render_query_trace(trace: dict) -> None:
    st.markdown("**1. Embed the question** (same model as the chunks)")
    st.code(f"dim={trace['query_embedding_dim']}  vector[:8]={trace['query_embedding_preview']}")
    st.markdown(f"**2. Similarity search** — top_k={trace['top_k']}, cutoff={trace['cutoff']}")
    md_table(
        [
            {"rank": i, "score": round(c["source"].score, 3),
             "kept": "✔" if c["kept"] else "✘ below cutoff",
             "source": c["source"].source_id, "section": c["source"].section,
             "text": c["source"].text}
            for i, c in enumerate(trace["candidates"], 1)
        ],
    )
    if trace["prompt"]:
        st.markdown("**3. Prompt sent to the LLM** (retrieved context + question)")
        st.code(trace["prompt"], language="text")
    else:
        st.warning("3. No chunk passed the cutoff, so the LLM was not called (grounding).")


with tab_chat:
    messages = st.session_state.setdefault("messages", [])
    for m in messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("trace") and show_trace:
                with st.expander("How this answer was produced"):
                    render_query_trace(m["trace"])
    if question := st.chat_input("Ask about the ingested documents"):
        messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            if service.store.count() == 0:
                text, trace = "Nothing is ingested yet. Use the Ingest tab first.", None
            else:
                with st.spinner("Retrieving and generating..."):
                    result = service.answer(question)
                text, trace = result.answer, result.trace
                if result.sources:
                    text += "\n\n**Sources:** " + "; ".join(
                        f"{s.title} §{s.section} ({s.score:.2f})" for s in result.sources
                    )
            st.markdown(text)
            if trace and show_trace:
                with st.expander("How this answer was produced", expanded=True):
                    render_query_trace(trace)
        messages.append({"role": "assistant", "content": text, "trace": trace})

with tab_ingest:
    st.subheader("Upload files")
    files = st.file_uploader("Markdown or text files", type=["md", "txt"], accept_multiple_files=True)
    if files and st.button("Ingest uploaded files", type="primary"):
        with tempfile.TemporaryDirectory() as tmp:
            for f in files:
                path = Path(tmp) / f.name
                path.write_bytes(f.getvalue())
                with st.status(f"Ingesting {f.name}", expanded=True):
                    render_ingest_trace(
                        ingest_mod.ingest_file(service.store, service.embed_model, path)
                    )
    st.divider()
    st.subheader("Sample documents")
    st.caption(f"Folder: {config.DOCS_DIR}")
    if st.button("Ingest sample documents"):
        st.json(ingest_mod.ingest(service.store, service.embed_model))

with tab_index:
    docs = service.store.list_documents()
    md_table(docs)
    options = ["(all)"] + [d["doc_id"] for d in docs]
    pick = st.selectbox("Show chunks of", options)
    for c in service.store.list_chunks(None if pick == "(all)" else pick)[:50]:
        with st.expander(f"{c['doc_id']} §{c['section']}"):
            st.text(c["text"])
            st.caption(f"vector dim={c['embedding_dim']}  vector[:8]={c['embedding_preview']}")
