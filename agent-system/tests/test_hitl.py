import pytest
from langchain_core.messages import AIMessage

from agents.agent import build_agent
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


def _chat(mcp_service) -> ChatService:
    memory = mcp_service.settings.memory_database_path
    app = build_agent(
        mcp_service.settings,
        model=CreateTicketModel(),
        checkpointer=create_checkpointer(memory),
    )
    return ChatService(app, ConversationStore(memory))


def test_write_is_paused_until_approved(mcp_service) -> None:
    chat = _chat(mcp_service)
    before = mcp_service.ticket_count()
    thread_id = chat.start_conversation("E104")

    turn = chat.send(thread_id, "E104", "My VPN isn't connecting, please raise a ticket.")

    assert turn["pending_approval"] is True
    assert mcp_service.ticket_count() == before
    assert chat.pending_approval(thread_id, "E104")["args"] == DRAFT

    done = chat.resume(thread_id, "E104", "approve")

    assert done["answer"] == "All done."
    assert mcp_service.ticket_count() == before + 1
    assert chat.pending_approval(thread_id, "E104") is None
    created = mcp_service.repository.list_my_tickets("E104").tickets
    assert any(t.title == DRAFT["title"] and t.status == "open" for t in created)


def test_edit_creates_ticket_with_edited_arguments(mcp_service) -> None:
    chat = _chat(mcp_service)
    thread_id = chat.start_conversation("E104")
    chat.send(thread_id, "E104", "raise a ticket")

    chat.resume(
        thread_id, "E104", "edit", {**DRAFT, "title": "VPN down at home", "priority": "high"}
    )

    created = mcp_service.repository.list_my_tickets("E104").tickets
    assert any(t.title == "VPN down at home" and t.priority == "high" for t in created)


def test_reject_writes_nothing(mcp_service) -> None:
    chat = _chat(mcp_service)
    before = mcp_service.ticket_count()
    thread_id = chat.start_conversation("E104")
    chat.send(thread_id, "E104", "raise a ticket")

    chat.resume(thread_id, "E104", "reject")

    assert mcp_service.ticket_count() == before
    assert chat.pending_approval(thread_id, "E104") is None


def test_resume_without_pending_approval_fails(mcp_service) -> None:
    chat = _chat(mcp_service)
    thread_id = chat.start_conversation("E104")

    with pytest.raises(ValueError):
        chat.resume(thread_id, "E104", "approve")
