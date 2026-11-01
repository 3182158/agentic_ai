from datetime import date, timedelta

from langchain_core.messages import AIMessage

from agents.agent import build_agent
from memory.checkpointer import create_checkpointer
from memory.service import ChatService
from memory.store import ConversationStore


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


MONDAY = _next_monday()
TUESDAY = MONDAY + timedelta(days=1)


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


def test_apply_leave_requires_approval_before_writing(mcp_service) -> None:
    memory = mcp_service.settings.memory_database_path
    app = build_agent(
        mcp_service.settings,
        model=LeaveModel(),
        checkpointer=create_checkpointer(memory),
    )
    chat = ChatService(app, ConversationStore(memory))
    thread_id = chat.start_conversation("E104")

    turn = chat.send(thread_id, "E104", "I want leave next Monday and Tuesday")

    assert turn["pending_approval"] is True
    assert len(mcp_service.repository.get_leave_history("E104").requests) == 3

    chat.resume(thread_id, "E104", "approve")

    assert len(mcp_service.repository.get_leave_history("E104").requests) == 4
