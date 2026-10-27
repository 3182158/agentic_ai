import sqlite3
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from agents.agent import build_agent
from build_database import build_database
from config import Settings
from data.repository import HelpdeskRepository
from memory.checkpointer import create_checkpointer
from memory.service import ChatService
from memory.store import ConversationStore

DRAFT = {
    "title": "VPN not connecting",
    "description": "The VPN fails to connect from home.",
    "category": "VPN",
    "priority": "medium",
}


class CreateTicketModel:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"name": "create_ticket", "args": DRAFT, "id": "c1", "type": "tool_call"}],
            )
        return AIMessage(content="All done.")


def _service(tmp_path: Path) -> tuple[ChatService, Path]:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    memory = tmp_path / "memory.sqlite3"
    app = build_agent(
        Settings(database, "E104", "test-model", 6),
        HelpdeskRepository(database),
        model=CreateTicketModel(),
        checkpointer=create_checkpointer(memory),
    )
    return ChatService(app, ConversationStore(memory)), database


def _ticket_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        return connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]


def test_write_is_paused_until_approved(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    before = _ticket_count(database)
    thread_id = service.start_conversation("E104")

    turn = service.send(thread_id, "E104", "My VPN isn't connecting, please raise a ticket.")

    assert turn["pending_approval"] is True
    assert _ticket_count(database) == before
    assert service.pending_approval(thread_id, "E104")["args"] == DRAFT

    done = service.resume(thread_id, "E104", "approve")

    assert done["answer"] == "All done."
    assert _ticket_count(database) == before + 1
    assert service.pending_approval(thread_id, "E104") is None
    created = HelpdeskRepository(database).list_my_tickets("E104").tickets
    assert any(t.title == DRAFT["title"] and t.status == "open" for t in created)


def test_edit_creates_ticket_with_edited_arguments(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    thread_id = service.start_conversation("E104")
    service.send(thread_id, "E104", "raise a ticket")

    service.resume(
        thread_id, "E104", "edit", {**DRAFT, "title": "VPN down at home", "priority": "high"}
    )

    created = HelpdeskRepository(database).list_my_tickets("E104").tickets
    assert any(t.title == "VPN down at home" and t.priority == "high" for t in created)


def test_reject_writes_nothing(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    before = _ticket_count(database)
    thread_id = service.start_conversation("E104")
    service.send(thread_id, "E104", "raise a ticket")

    service.resume(thread_id, "E104", "reject")

    assert _ticket_count(database) == before
    assert service.pending_approval(thread_id, "E104") is None


def test_resume_without_pending_approval_fails(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    thread_id = service.start_conversation("E104")

    with pytest.raises(ValueError):
        service.resume(thread_id, "E104", "approve")


def test_repository_create_ticket_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    repository = HelpdeskRepository(database)
    before = _ticket_count(database)

    first = repository.create_ticket("E104", "Title here", "Some description", "VPN", "low", "key-1")
    again = repository.create_ticket("E104", "Title here", "Some description", "VPN", "low", "key-1")

    assert first.created is True and again.created is False
    assert first.ticket_id == again.ticket_id
    assert _ticket_count(database) == before + 1
