from datetime import date, timedelta
from pathlib import Path

from langchain_core.messages import AIMessage

from agents.agent import build_agent
from build_database import build_database
from config import Settings
from data.repository import HelpdeskRepository
from memory.checkpointer import create_checkpointer
from memory.service import ChatService
from memory.store import ConversationStore


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


MONDAY = _next_monday()
TUESDAY = MONDAY + timedelta(days=1)


def _repo(tmp_path: Path) -> HelpdeskRepository:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    return HelpdeskRepository(database)


def test_leave_history_is_scoped_to_the_employee(tmp_path: Path) -> None:
    result = _repo(tmp_path).get_leave_history("E104")

    assert [r.request_id for r in result.requests] == ["LR-1015", "LR-1014", "LR-1013"]


def test_apply_leave_creates_pending_request_and_is_idempotent(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    first = repo.apply_leave("E104", "annual", MONDAY.isoformat(), TUESDAY.isoformat(), "Trip", "k1")
    again = repo.apply_leave("E104", "annual", MONDAY.isoformat(), TUESDAY.isoformat(), "Trip", "k1")

    assert first.created and first.days == 2 and first.status == "pending"
    assert not again.created and again.request_id == first.request_id
    history = repo.get_leave_history("E104").requests
    assert [r.request_id for r in history].count(first.request_id) == 1


def test_apply_leave_rejects_invalid_requests(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saturday = MONDAY - timedelta(days=2)

    assert not repo.apply_leave("E104", "annual", TUESDAY.isoformat(), MONDAY.isoformat(), "", "a").created
    assert not repo.apply_leave("E104", "annual", "2020-01-06", "2020-01-07", "", "b").created
    assert not repo.apply_leave("E104", "annual", saturday.isoformat(), (saturday + timedelta(1)).isoformat(), "", "c").created
    too_long = repo.apply_leave("E104", "annual", MONDAY.isoformat(), (MONDAY + timedelta(days=60)).isoformat(), "", "d")
    assert not too_long.created and "Insufficient" in too_long.message


def test_apply_leave_blocks_overlap(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.apply_leave("E104", "annual", MONDAY.isoformat(), TUESDAY.isoformat(), "", "k1")

    overlap = repo.apply_leave("E104", "annual", TUESDAY.isoformat(), TUESDAY.isoformat(), "", "k2")

    assert not overlap.created and "overlap" in overlap.message


class LeaveModel:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            args = {
                "leave_type": "annual",
                "start_date": MONDAY.isoformat(),
                "end_date": TUESDAY.isoformat(),
                "reason": "Trip",
            }
            return AIMessage(
                content="",
                tool_calls=[{"name": "apply_leave", "args": args, "id": "l1", "type": "tool_call"}],
            )
        return AIMessage(content="Submitted.")


def test_apply_leave_requires_approval_before_writing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    memory = tmp_path / "memory.sqlite3"
    app = build_agent(
        Settings(repo.database_path, "E104", "test-model", 6),
        repo,
        model=LeaveModel(),
        checkpointer=create_checkpointer(memory),
    )
    service = ChatService(app, ConversationStore(memory))
    thread_id = service.start_conversation("E104")

    turn = service.send(thread_id, "E104", "I want leave next Monday and Tuesday")

    assert turn["pending_approval"] is True
    assert len(repo.get_leave_history("E104").requests) == 3

    service.resume(thread_id, "E104", "approve")

    assert len(repo.get_leave_history("E104").requests) == 4
