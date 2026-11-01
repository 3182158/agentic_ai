"""Environment-backed configuration for the local workshop agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MEMORY_DATABASE = ROOT_DIR / ".data" / "chat_memory.sqlite3"
DEFAULT_MCP_URL = "http://127.0.0.1:9000/mcp"


@dataclass(frozen=True)
class Settings:
    """Configuration injected at the application boundary."""

    employee_id: str
    model_name: str
    max_model_steps: int
    memory_database_path: Path = DEFAULT_MEMORY_DATABASE
    mcp_url: str = DEFAULT_MCP_URL
    mcp_secret: str = ""


def get_settings() -> Settings:
    """Load local settings; identity comes from trusted app configuration."""
    load_dotenv(ROOT_DIR / ".env")
    return Settings(
        employee_id=os.getenv("HELPDESK_DEMO_EMPLOYEE_ID", "E104").strip().upper(),
        model_name=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        max_model_steps=max(1, int(os.getenv("HELPDESK_MAX_MODEL_STEPS", "6"))),
        memory_database_path=Path(
            os.getenv("HELPDESK_MEMORY_DATABASE_PATH", str(DEFAULT_MEMORY_DATABASE))
        ).expanduser(),
        mcp_url=(os.getenv("HELPDESK_MCP_URL") or DEFAULT_MCP_URL).strip(),
        mcp_secret=os.getenv("HELPDESK_MCP_SECRET", "").strip(),
    )
