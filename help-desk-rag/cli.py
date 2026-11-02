"""Interactive CLI chat for the help-desk RAG that shows the pipeline's internals.

    python help-desk-rag/cli.py

Type a question to run RAG; slash commands ingest files and inspect the index.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import ingest as ingest_mod  # noqa: E402
from rag import RagResult, RagService  # noqa: E402

console = Console()

HELP = """\
[bold]Commands[/bold]
  [cyan]/ingest [path][/cyan]   ingest a file or folder (default: mock-data/documents)
  [cyan]/rebuild[/cyan]         wipe the index and re-ingest the default documents
  [cyan]/docs[/cyan]            list ingested documents
  [cyan]/chunks [doc_id][/cyan] show stored chunks (text + vector preview)
  [cyan]/stats[/cyan]           index and retrieval settings
  [cyan]/topk N[/cyan]          set how many chunks are retrieved
  [cyan]/cutoff X[/cyan]        set the minimum similarity score (0-1)
  [cyan]/trace on|off[/cyan]    show or hide the step-by-step internals
  [cyan]/help[/cyan], [cyan]/exit[/cyan]
Anything else is treated as a question."""


def show_ingest_trace(trace: dict) -> None:
    console.print(Panel(
        f"[bold]{trace['doc_id']}[/bold]  ({trace['characters']} chars)\n"
        + "\n".join(f"{k}: {v}" for k, v in trace["metadata"].items()),
        title="1-2. LOAD + PARSE (front matter -> metadata)",
    ))
    table = Table(title=f"3. CHUNK -> 4. EMBED ({len(trace['chunks'])} chunks)")
    for col in ("#", "section", "chars", "text (start)", "vector dim", "vector[:8]"):
        table.add_column(col)
    for i, c in enumerate(trace["chunks"], 1):
        table.add_row(
            str(i), c["section"], str(c["chars"]), c["text"][:60].replace("\n", " ") + "…",
            str(c["embedding_dim"]), str(c["embedding_preview"]),
        )
    console.print(table)
    console.print("[green]5. STORE[/green] chunks + vectors written to SQLite\n")


def show_query_trace(result: RagResult) -> None:
    t = result.trace
    console.print(Panel(
        f"{t['question']}\nvector dim={t['query_embedding_dim']}  "
        f"vector[:8]={t['query_embedding_preview']}",
        title="1. EMBED QUESTION (same model as chunks)",
    ))
    table = Table(title=f"2. SIMILARITY SEARCH (top_k={t['top_k']}, cutoff={t['cutoff']})")
    for col in ("rank", "score", "kept", "source", "section"):
        table.add_column(col)
    for i, c in enumerate(t["candidates"], 1):
        s = c["source"]
        table.add_row(str(i), f"{s.score:.3f}", "✔" if c["kept"] else "✘ below cutoff",
                      s.source_id, s.section)
    console.print(table)
    if t["prompt"]:
        console.print(Panel(t["prompt"], title="3. PROMPT SENT TO LLM (context + question)"))
    else:
        console.print("[yellow]3. No chunk passed the cutoff -> LLM not called (grounding).[/yellow]")


def answer(service: RagService, question: str, trace: bool) -> None:
    result = service.answer(question)
    if trace:
        show_query_trace(result)
    style = "green" if result.grounded else "yellow"
    console.print(Panel(Markdown(result.answer), title=f"ANSWER (grounded={result.grounded})",
                        border_style=style))
    for s in result.sources:
        console.print(f"  • {s.title} v{s.version} §{s.section}  (score {s.score:.3f})")


def do_ingest(service: RagService, arg: str) -> None:
    target = Path(arg).expanduser() if arg else config.DOCS_DIR
    if target.is_dir():
        stats = ingest_mod.ingest(service.store, service.embed_model, target)
        console.print(f"Ingested folder {target}: {stats}")
    elif target.is_file():
        show_ingest_trace(ingest_mod.ingest_file(service.store, service.embed_model, target))
    else:
        console.print(f"[red]Not found:[/red] {target}")


def handle_command(service: RagService, command: str, arg: str, state: dict) -> bool:
    if command in {"exit", "quit"}:
        return False
    if command == "help":
        console.print(HELP)
    elif command == "ingest":
        do_ingest(service, arg)
    elif command == "rebuild":
        service.store.clear()
        console.print(ingest_mod.ingest(service.store, service.embed_model))
    elif command == "docs":
        table = Table(title="Documents")
        for col in ("doc_id", "source_id", "version", "chunks"):
            table.add_column(col)
        for d in service.store.list_documents():
            table.add_row(d["doc_id"], d["source_id"], d["version"], str(d["chunks"]))
        console.print(table)
    elif command == "chunks":
        for c in service.store.list_chunks(arg or None)[:30]:
            console.print(Panel(c["text"], title=f"{c['doc_id']} §{c['section']}",
                                subtitle=f"vector dim={c['embedding_dim']} {c['embedding_preview']}"))
    elif command == "stats":
        console.print(
            f"documents={len(service.store.list_documents())} chunks={service.store.count()} "
            f"db={config.DB_PATH}\nembed={config.EMBED_MODEL} llm={config.LLM_MODEL} "
            f"top_k={service.top_k} cutoff={service.cutoff} trace={state['trace']}"
        )
    elif command == "topk" and arg.isdigit():
        service.top_k = int(arg)
    elif command == "cutoff":
        try:
            service.cutoff = float(arg)
        except ValueError:
            console.print("[red]Usage: /cutoff 0.3[/red]")
    elif command == "trace" and arg in {"on", "off"}:
        state["trace"] = arg == "on"
    else:
        console.print("[red]Unknown command.[/red] Type /help")
    return True


def main() -> None:
    service = RagService.from_env()
    state = {"trace": True}
    console.print(Panel("Help-desk RAG chat. Ask a question or type /help.", title="RAG demo"))
    if service.store.count() == 0:
        console.print("[yellow]Index is empty. Run /ingest to load the sample documents.[/yellow]")
    while True:
        try:
            text = console.input("[bold blue]you>[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        try:
            if text.startswith("/"):
                parts = text[1:].split(maxsplit=1)
                if not handle_command(service, parts[0].casefold(), parts[1] if len(parts) > 1 else "", state):
                    break
            elif service.store.count() == 0:
                console.print("[yellow]Nothing ingested yet. Use /ingest first.[/yellow]")
            else:
                answer(service, text, state["trace"])
        except Exception as exc:  # keep the chat alive on API/file errors
            console.print(f"[red]Error:[/red] {exc}")


if __name__ == "__main__":
    main()
