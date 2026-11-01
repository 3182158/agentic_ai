"""Run the real server on a free local port and call it with the MCP client."""

from __future__ import annotations

import asyncio
import socket
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "mock-data" / "sqlite"))

from build_database import build_database  # noqa: E402

from ticket_leave_mcp.config import Settings  # noqa: E402
from ticket_leave_mcp.server import create_app  # noqa: E402

SECRET = "test-secret-test-secret-test-secret-123"


def make_token(employee_id: str, *, secret: str = SECRET, expires_in: int = 300) -> str:
    exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return jwt.encode({"sub": employee_id, "exp": exp}, secret, algorithm="HS256")


@pytest.fixture
def server_url(tmp_path: Path):
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    settings = Settings(database_path=database, jwt_secret=SECRET, port=port)
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def call_tool(server_url: str):
    def call(name: str, arguments: dict | None = None, headers: dict | None = None):
        async def run():
            async with streamablehttp_client(server_url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(name, arguments or {})

        return asyncio.run(run())

    return call
