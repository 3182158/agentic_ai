"""Make this workshop's hyphenated source directory importable in tests."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "agent-system"))
sys.path.insert(0, str(ROOT_DIR / "mock-data" / "sqlite"))
