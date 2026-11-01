"""Environment-backed server configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVICE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = SERVICE_DIR.parent
DEFAULT_DATABASE = REPO_DIR / "mock-data" / "sqlite" / "acme_helpdesk.sqlite3"
MIN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class Settings:
    database_path: Path
    jwt_secret: str
    host: str = "127.0.0.1"
    port: int = 9000


def get_settings() -> Settings:
    load_dotenv(REPO_DIR / ".env")
    load_dotenv(SERVICE_DIR / ".env")
    secret = os.getenv("HELPDESK_MCP_SECRET", "").strip()
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"HELPDESK_MCP_SECRET must be set to at least {MIN_SECRET_LENGTH} characters."
        )
    return Settings(
        database_path=Path(os.getenv("HELPDESK_DATABASE_PATH") or DEFAULT_DATABASE).expanduser(),
        jwt_secret=secret,
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "9000")),
    )
