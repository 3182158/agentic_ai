from datetime import date, timedelta
from pathlib import Path

import pytest

from build_database import build_database
from ticket_leave_mcp.repository import HelpdeskRepository


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


MONDAY = _next_monday()
TUESDAY = MONDAY + timedelta(days=1)


@pytest.fixture
def repository(tmp_path: Path) -> HelpdeskRepository:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    return HelpdeskRepository(database)


def test_ticket_lookup_returns_seeded_status(repository: HelpdeskRepository) -> None:
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

    assert {ticket.ticket_id for ticket in result.tickets} == {"INC-1042", "INC-1050", "INC-1058"}


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


def test_create_ticket_is_idempotent(repository: HelpdeskRepository) -> None:
    args = ("E104", "VPN keeps dropping", "VPN drops every ten minutes.", "VPN", "medium")
    first = repository.create_ticket(*args, idempotency_key="k1")
    second = repository.create_ticket(*args, idempotency_key="k1")

    assert first.created is True
    assert second.created is False
    assert second.ticket_id == first.ticket_id


def test_leave_history_is_scoped_to_the_employee(repository: HelpdeskRepository) -> None:
    result = repository.get_leave_history("E104")

    assert [r.request_id for r in result.requests] == ["LR-1015", "LR-1014", "LR-1013"]


def test_apply_leave_creates_pending_request_and_is_idempotent(
    repository: HelpdeskRepository,
) -> None:
    args = ("E104", "annual", MONDAY.isoformat(), TUESDAY.isoformat(), "Trip")
    first = repository.apply_leave(*args, idempotency_key="k1")
    again = repository.apply_leave(*args, idempotency_key="k1")

    assert first.created and first.days == 2 and first.status == "pending"
    assert not again.created and again.request_id == first.request_id
    history = repository.get_leave_history("E104").requests
    assert [r.request_id for r in history].count(first.request_id) == 1


def test_apply_leave_rejects_invalid_requests(repository: HelpdeskRepository) -> None:
    saturday = MONDAY - timedelta(days=2)

    def apply(start: str, end: str, key: str):
        return repository.apply_leave("E104", "annual", start, end, "", key)

    assert not apply(TUESDAY.isoformat(), MONDAY.isoformat(), "a").created
    assert not apply("2020-01-06", "2020-01-07", "b").created
    assert not apply(saturday.isoformat(), (saturday + timedelta(1)).isoformat(), "c").created
    too_long = apply(MONDAY.isoformat(), (MONDAY + timedelta(days=60)).isoformat(), "d")
    assert not too_long.created and "Insufficient" in too_long.message


def test_apply_leave_blocks_overlap(repository: HelpdeskRepository) -> None:
    repository.apply_leave("E104", "annual", MONDAY.isoformat(), TUESDAY.isoformat(), "", "k1")

    overlap = repository.apply_leave(
        "E104", "annual", TUESDAY.isoformat(), TUESDAY.isoformat(), "", "k2"
    )

    assert not overlap.created and "overlap" in overlap.message
