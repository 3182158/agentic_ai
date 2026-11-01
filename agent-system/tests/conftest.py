"""Shared test setup: importable source dirs and a real MCP service on a local port."""

import socket
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "agent-system"))
sys.path.insert(0, str(ROOT_DIR / "mock-data" / "sqlite"))
sys.path.insert(0, str(ROOT_DIR / "ticket-and-leave-manager-service" / "src"))

from build_database import build_database  # noqa: E402
from config import Settings  # noqa: E402
from ticket_leave_mcp.config import Settings as ServiceSettings  # noqa: E402
from ticket_leave_mcp.repository import HelpdeskRepository  # noqa: E402
from ticket_leave_mcp.server import create_app  # noqa: E402

SECRET = "test-secret-test-secret-test-secret-123"


@dataclass
class RunningService:
    """The real MCP service on a free local port, backed by an isolated fixture database."""

    settings: Settings
    database: Path
    server: uvicorn.Server
    thread: threading.Thread

    @property
    def repository(self) -> HelpdeskRepository:
        """Read the service's data directly, to assert on what the agent wrote."""
        return HelpdeskRepository(self.database)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)

    def ticket_count(self) -> int:
        with sqlite3.connect(self.database) as connection:
            return connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]


def _start(directory: Path) -> RunningService:
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / "helpdesk.sqlite3"
    build_database(database)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app = create_app(ServiceSettings(database, SECRET, port=port))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    settings = Settings(
        "E104",
        "test-model",
        4,
        memory_database_path=directory / "memory.sqlite3",
        mcp_url=f"http://127.0.0.1:{port}/mcp",
        mcp_secret=SECRET,
    )
    return RunningService(settings, database, server, thread)


@pytest.fixture
def start_mcp_service(tmp_path: Path):
    """Factory for tests that must change the server before it starts."""
    started: list[RunningService] = []

    def start() -> RunningService:
        running = _start(tmp_path / f"service-{len(started)}")
        started.append(running)
        return running

    yield start
    for running in started:
        running.stop()


@pytest.fixture
def mcp_service(start_mcp_service) -> RunningService:
    return start_mcp_service()
