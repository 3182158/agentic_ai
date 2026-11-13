from dataclasses import replace
from datetime import date, timedelta

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agents.agent import build_agent
from memory.checkpointer import create_checkpointer
from memory.service import ApprovalDecision, ChatService
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


class TicketAndLeaveModel:
    """Draft both writes directly or through parallel specialist delegations."""

    def __init__(self, names=()) -> None:
        self.names = set(names)

    def bind_tools(self, tools, **kwargs):
        return TicketAndLeaveModel(
            getattr(tool, "name", None) or tool["function"]["name"] for tool in tools
        )

    def invoke(self, messages, *args, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="All done.")
        monday = date.today() + timedelta(days=7 - date.today().weekday())
        leave = {
            "leave_type": "annual",
            "start_date": monday.isoformat(),
            "end_date": (monday + timedelta(days=2)).isoformat(),
            "reason": "Time off",
        }
        if "ask_it_specialist" in self.names:
            calls = [
                ("ask_it_specialist", {"request": "Raise a VPN ticket"}),
                ("ask_hr_specialist", {"request": "Request three days off"}),
            ]
        else:
            calls = [
                (name, args) for name, args in
                [("create_ticket", DRAFT), ("apply_leave", leave)]
                if name in self.names
            ]
        return AIMessage(
            content="",
            tool_calls=[
                {"name": name, "args": args, "id": f"call-{i}", "type": "tool_call"}
                for i, (name, args) in enumerate(calls)
            ],
        )


def _combined_chat(mcp_service, multi_agent):
    memory = mcp_service.settings.memory_database_path
    app = build_agent(
        replace(mcp_service.settings, multi_agent=multi_agent),
        model=TicketAndLeaveModel(),
        checkpointer=create_checkpointer(memory),
    )
    return ChatService(app, ConversationStore(memory))


@pytest.mark.parametrize("multi_agent", [False, True])
@pytest.mark.parametrize("ticket_decision", ["approve", "edit", "reject"])
def test_each_pending_write_gets_its_own_decision(mcp_service, multi_agent, ticket_decision):
    chat = _combined_chat(mcp_service, multi_agent)
    thread_id = chat.start_conversation("E104")
    tickets_before = mcp_service.ticket_count()
    leaves_before = len(mcp_service.repository.get_leave_history("E104").requests)
    chat.send(thread_id, "E104", "My VPN is broken and I want three days off next week.")

    pending = chat.pending_approvals(thread_id, "E104")
    assert {action["name"] for action in pending} == {"create_ticket", "apply_leave"}
    assert len({action["interrupt_id"] for action in pending}) == (2 if multi_agent else 1)
    assert mcp_service.ticket_count() == tickets_before
    assert len(mcp_service.repository.get_leave_history("E104").requests) == leaves_before
    decisions: list[ApprovalDecision] = [
        {
            "interrupt_id": action["interrupt_id"],
            "action_index": action["action_index"],
            "decision": ticket_decision if action["name"] == "create_ticket" else "approve",
            "edited_args": {**action["args"], "title": "Edited VPN ticket"},
        }
        for action in pending
    ]

    # Input order must not change which action receives a decision.
    done = chat.resume_approvals(thread_id, "E104", list(reversed(decisions)))

    assert done["pending_approval"] is False
    assert chat.pending_approvals(thread_id, "E104") == []
    assert mcp_service.ticket_count() == tickets_before + (ticket_decision != "reject")
    assert len(mcp_service.repository.get_leave_history("E104").requests) == leaves_before + 1
    if ticket_decision == "edit":
        assert any(
            ticket.title == "Edited VPN ticket"
            for ticket in mcp_service.repository.list_my_tickets("E104").tickets
        )


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "stale", "unknown"])
def test_invalid_approval_batch_leaves_all_writes_paused(mcp_service, invalid):
    chat = _combined_chat(mcp_service, True)
    thread_id = chat.start_conversation("E104")
    chat.send(thread_id, "E104", "Raise a ticket and request leave.")
    pending = chat.pending_approvals(thread_id, "E104")
    decisions: list[ApprovalDecision] = [
        {
            "interrupt_id": action["interrupt_id"],
            "action_index": action["action_index"],
            "decision": "approve",
        }
        for action in pending
    ]
    if invalid == "missing":
        decisions.pop()
    elif invalid == "duplicate":
        decisions.append(decisions[0])
    elif invalid == "stale":
        decisions[0]["interrupt_id"] = "stale"
    else:
        decisions[0]["decision"] = "unknown"

    with pytest.raises(ValueError):
        chat.resume_approvals(thread_id, "E104", decisions)

    assert chat.pending_approvals(thread_id, "E104") == pending
    with pytest.raises(ValueError, match="every pending action"):
        chat.resume(thread_id, "E104", "approve")
    assert chat.pending_approvals(thread_id, "E104") == pending
