"""Custom conversation layer: sessions, display messages, search, analytics.

Agent state (messages, tool calls) lives in the LangGraph checkpointer keyed by
``thread_id``. This store only keeps the clean transcript shown in the UI.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_TITLE = "New conversation"

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    thread_id  TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_user
    ON conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id  TEXT NOT NULL REFERENCES conversations (thread_id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    tool_names TEXT NOT NULL DEFAULT '[]',
    is_error   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages (thread_id, id);
"""


class ConversationNotFound(LookupError):
    """Unknown thread, or one the caller does not own (indistinguishable by design)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ConversationStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    # -- sessions -----------------------------------------------------------------

    def create_conversation(self, user_id: str, title: str = DEFAULT_TITLE) -> str:
        thread_id = uuid.uuid4().hex
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversations (thread_id, user_id, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (thread_id, user_id, title, now, now),
            )
        return thread_id

    def get_conversation(self, thread_id: str, user_id: str) -> dict[str, Any]:
        """Return the conversation if ``user_id`` owns it; otherwise raise."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE thread_id = ? AND user_id = ?"
                " AND deleted_at IS NULL",
                (thread_id, user_id),
            ).fetchone()
        if row is None:
            raise ConversationNotFound(thread_id)
        return dict(row)

    def list_conversations(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM conversations WHERE user_id = ? AND deleted_at IS NULL"
                " ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def rename_conversation(self, thread_id: str, user_id: str, title: str) -> None:
        self.get_conversation(thread_id, user_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE thread_id = ?",
                (title.strip()[:80] or DEFAULT_TITLE, _now(), thread_id),
            )

    def delete_conversation(self, thread_id: str, user_id: str) -> None:
        """Soft-delete so analytics history survives; the transcript is hidden."""
        self.get_conversation(thread_id, user_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE conversations SET deleted_at = ? WHERE thread_id = ?", (_now(), thread_id)
            )

    # -- display messages ---------------------------------------------------------

    def add_message(
        self,
        thread_id: str,
        user_id: str,
        role: str,
        content: str,
        *,
        tool_names: Iterable[str] = (),
        is_error: bool = False,
    ) -> int:
        conversation = self.get_conversation(thread_id, user_id)
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages (thread_id, role, content, tool_names, is_error, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, role, content, json.dumps(list(tool_names)), int(is_error), now),
            )
            if role == "user" and conversation["title"] == DEFAULT_TITLE:
                title = " ".join(content.split())[:60] or DEFAULT_TITLE
                connection.execute(
                    "UPDATE conversations SET title = ? WHERE thread_id = ?", (title, thread_id)
                )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE thread_id = ?", (now, thread_id)
            )
            return int(cursor.lastrowid)

    def get_messages(self, thread_id: str, user_id: str) -> list[dict[str, Any]]:
        self.get_conversation(thread_id, user_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, role, content, tool_names, is_error, created_at"
                " FROM messages WHERE thread_id = ? ORDER BY id",
                (thread_id,),
            ).fetchall()
        messages = [dict(row) for row in rows]
        for message in messages:
            message["tool_names"] = json.loads(message["tool_names"])
            message["is_error"] = bool(message["is_error"])
        return messages

    # -- search -------------------------------------------------------------------

    def search(self, user_id: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Case-insensitive substring search over the user's titles and messages."""
        term = query.strip()
        if not term:
            return []
        pattern = f"%{_escape_like(term)}%"
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT c.thread_id, c.title, c.updated_at, m.id AS message_id, m.role, m.content"
                " FROM conversations AS c LEFT JOIN messages AS m ON m.thread_id = c.thread_id"
                " AND m.content LIKE ? ESCAPE '\\'"
                " WHERE c.user_id = ? AND c.deleted_at IS NULL"
                " AND (m.id IS NOT NULL OR c.title LIKE ? ESCAPE '\\')"
                " ORDER BY c.updated_at DESC, m.id LIMIT ?",
                (pattern, user_id, pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- analytics ----------------------------------------------------------------

    def analytics(self, user_id: str | None = None) -> dict[str, Any]:
        """Usage summary; scoped to one user, or all users when ``user_id`` is None."""
        scope = "" if user_id is None else " AND c.user_id = ?"
        args: tuple[Any, ...] = () if user_id is None else (user_id,)
        with self._connect() as connection:
            totals = connection.execute(
                "SELECT COUNT(DISTINCT c.thread_id) AS conversations,"
                " COALESCE(SUM(m.role = 'user'), 0) AS user_messages,"
                " COALESCE(SUM(m.role = 'assistant'), 0) AS assistant_messages,"
                " COALESCE(SUM(m.is_error), 0) AS errors"
                " FROM conversations AS c LEFT JOIN messages AS m ON m.thread_id = c.thread_id"
                f" WHERE c.deleted_at IS NULL{scope}",
                args,
            ).fetchone()
            tools = connection.execute(
                "SELECT j.value AS tool, COUNT(*) AS calls FROM messages AS m"
                " JOIN conversations AS c ON c.thread_id = m.thread_id,"
                " json_each(m.tool_names) AS j"
                f" WHERE c.deleted_at IS NULL{scope} GROUP BY j.value ORDER BY calls DESC",
                args,
            ).fetchall()
        conversations = totals["conversations"]
        return {
            "conversations": conversations,
            "user_messages": totals["user_messages"],
            "assistant_messages": totals["assistant_messages"],
            "errors": totals["errors"],
            "avg_user_messages_per_conversation": (
                round(totals["user_messages"] / conversations, 2) if conversations else 0.0
            ),
            "tool_usage": {row["tool"]: row["calls"] for row in tools},
        }
