"""LangGraph short-term memory backed by SQLite, keyed by ``thread_id``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


def create_checkpointer(database_path: Path | str) -> SqliteSaver:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Streamlit reruns script threads; SqliteSaver serialises access with its own lock.
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.execute("PRAGMA journal_mode = WAL")
    return SqliteSaver(connection)
