"""Cross-conversation memory: durable facts per employee, independent of thread_id."""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

MAX_FACT_LENGTH = 200
MAX_FACTS_PER_EMPLOYEE = 20
_SECRET_PATTERN = re.compile(
    r"password|passwd|passcode|\botp\b|\bpin\b|secret|token|api[_ -]?key|\b\d{6,}\b",
    re.IGNORECASE,
)


class LongTermMemory:
    """SQLite-backed facts namespaced by employee ID, so one user never reads another's."""

    def __init__(self, database_path: Path | str) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS employee_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                fact TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self._db.commit()

    def remember(self, employee_id: str, fact: str) -> str:
        fact = " ".join(fact.split())
        if not fact:
            return "Nothing to remember."
        if len(fact) > MAX_FACT_LENGTH:
            return f"Not saved: keep memories under {MAX_FACT_LENGTH} characters."
        if _SECRET_PATTERN.search(fact):
            return "Not saved: passwords, codes, tokens and numbers like IDs must not be stored."
        with self._lock:
            rows = self._db.execute(
                "SELECT fact FROM employee_memories WHERE employee_id = ?", (employee_id,)
            ).fetchall()
            if any(row[0].lower() == fact.lower() for row in rows):
                return "Already remembered."
            if len(rows) >= MAX_FACTS_PER_EMPLOYEE:
                return "Not saved: memory is full. Ask the user which memory to forget."
            self._db.execute(
                "INSERT INTO employee_memories (employee_id, fact, created_at) VALUES (?, ?, ?)",
                (employee_id, fact, datetime.now(timezone.utc).isoformat()),
            )
            self._db.commit()
        return "Saved."

    def list(self, employee_id: str) -> list[tuple[int, str]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, fact FROM employee_memories WHERE employee_id = ? ORDER BY id",
                (employee_id,),
            ).fetchall()
        return [(int(row[0]), str(row[1])) for row in rows]

    def forget(self, employee_id: str, memory_id: int) -> bool:
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM employee_memories WHERE id = ? AND employee_id = ?",
                (memory_id, employee_id),
            )
            self._db.commit()
        return cursor.rowcount > 0

    def forget_all(self, employee_id: str) -> int:
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM employee_memories WHERE employee_id = ?", (employee_id,)
            )
            self._db.commit()
        return cursor.rowcount
