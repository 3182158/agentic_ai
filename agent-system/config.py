"""Environment-backed configuration for the local workshop agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT_DIR / "mock-data" / "sqlite" / "acme_helpdesk.sqlite3"


@dataclass(frozen=True)
class Settings:
    """Configuration injected at the application boundary."""

    database_path: Path
    employee_id: str
    model_name: str
    max_model_steps: int


def get_settings() -> Settings:
    """Load local settings; identity comes from trusted app configuration."""
    load_dotenv(ROOT_DIR / ".env")
    return Settings(
        database_path=Path(os.getenv("HELPDESK_DATABASE_PATH", str(DEFAULT_DATABASE))).expanduser(),
        employee_id=os.getenv("HELPDESK_DEMO_EMPLOYEE_ID", "E104").strip().upper(),
        model_name=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        max_model_steps=max(1, int(os.getenv("HELPDESK_MAX_MODEL_STEPS", "6"))),
    )
