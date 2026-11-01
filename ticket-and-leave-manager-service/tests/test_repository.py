from pathlib import Path

import pytest

from build_database import build_database
from ticket_leave_mcp.repository import HelpdeskRepository


@pytest.fixture
def repository(tmp_path: Path) -> HelpdeskRepository:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    return HelpdeskRepository(database)


def test_ticket_lookup_returns_seeded_status(repository: HelpdeskRepository) -> None:
    result = repository.get_ticket_status("inc-1042", "E104")

    assert result.found is True
    assert result.status == "in_progress"


def test_employee_cannot_read_another_employees_ticket(repository: HelpdeskRepository) -> None:
    result = repository.get_ticket_status("INC-1043", "E104")

    assert result.found is False
    assert result.message == "You are not authorized to view this ticket."


def test_create_ticket_is_idempotent(repository: HelpdeskRepository) -> None:
    args = ("E104", "VPN keeps dropping", "VPN drops every ten minutes.", "VPN", "medium")
    first = repository.create_ticket(*args, idempotency_key="k1")
    second = repository.create_ticket(*args, idempotency_key="k1")

    assert first.created is True
    assert second.created is False
    assert second.ticket_id == first.ticket_id
