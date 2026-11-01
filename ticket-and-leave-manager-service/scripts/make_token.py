"""Print a signed JWT for an employee ID: uv run python scripts/make_token.py E104 [--ttl 3600]"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import jwt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ticket_leave_mcp.config import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a JWT for the helpdesk MCP server.")
    parser.add_argument("employee_id", help="Employee ID, e.g. E104")
    parser.add_argument("--ttl", type=int, default=3600, help="Lifetime in seconds (default 3600)")
    args = parser.parse_args()

    employee_id = args.employee_id.strip().upper()
    if not employee_id:
        parser.error("employee_id must not be empty")

    claims = {"sub": employee_id, "exp": int(time.time()) + args.ttl}
    print(jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256"))


if __name__ == "__main__":
    main()
