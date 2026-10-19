from pathlib import Path

import pytest

from build_database import build_database
from data.repository import HelpdeskRepository


@pytest.fixture

def repository(tmp_path: Path) -> HelpdeskRepository:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    return HelpdeskRepository(database)


def test_ticket_lookup_returns_seeded_status_and_priority(repository: HelpdeskRepository) -> None:
    result = repository.get_ticket_status("inc-1042", "E104")

    assert result.found is True
    assert result.status == "in_progress"
    assert result.priority == "high"
    assert result.assigned_to == "Meera Patel"


def test_unknown_ticket_is_not_invented(repository: HelpdeskRepository) -> None:
    result = repository.get_ticket_status("INC-9999", "E104")

    assert result.found is False
    assert result.message == "Ticket not found."


def test_employee_cannot_read_another_employees_ticket(repository: HelpdeskRepository) -> None:
    result = repository.get_ticket_status("INC-1043", "E104")

    assert result.found is False
    assert result.message == "You are not authorized to view this ticket."


def test_it_admin_can_read_any_ticket(repository: HelpdeskRepository) -> None:
    result = repository.get_ticket_status("INC-1043", "E102")

    assert result.found is True
    assert result.status == "open"


def test_my_tickets_are_scoped_to_current_employee(repository: HelpdeskRepository) -> None:
    result = repository.list_my_tickets("E104")

    assert {ticket.ticket_id for ticket in result.tickets} == {
        "INC-1042", "INC-1050", "INC-1058"
    }


def test_leave_balance_is_scoped_and_calculated(repository: HelpdeskRepository) -> None:
    result = repository.check_leave_balance("E104")

    assert result.found is True
    assert result.annual_remaining == 13
    assert result.sick_remaining == 8
    assert result.carry_forward_remaining == 4
    assert result.total_remaining == 25


def test_leave_balance_handles_employee_with_no_remaining_days(
    repository: HelpdeskRepository,
) -> None:
    result = repository.check_leave_balance("E109")

    assert result.found is True
    assert result.total_remaining == 0


def test_repository_rejects_missing_database(tmp_path: Path) -> None:
    repository = HelpdeskRepository(tmp_path / "missing.sqlite3")

    with pytest.raises(FileNotFoundError, match="Build it with"):
        repository.list_my_tickets("E104")
