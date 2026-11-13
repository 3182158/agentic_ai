from dataclasses import replace

from langchain_core.messages import AIMessage, ToolMessage

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


class RoleModel:
    """One fake model for every agent; it acts according to the tools bound to it."""

    def __init__(self, names=()) -> None:
        self.names = set(names)

    def bind_tools(self, tools, **kwargs):
        return RoleModel(getattr(t, "name", None) or t["function"]["name"] for t in tools)

    def invoke(self, messages, *args, **kwargs):
        last = messages[-1]
        if isinstance(last, ToolMessage):
            return AIMessage(content=f"Done: {last.content}")
        if "ask_it_specialist" in self.names:
            call = {"name": "ask_it_specialist", "args": {"request": "Raise a VPN ticket"}}
        else:
            call = {"name": "create_ticket", "args": DRAFT}
        return AIMessage(content="", tool_calls=[{**call, "id": "c1", "type": "tool_call"}])


def test_supervisor_routes_to_specialist_and_approval_bubbles_up(mcp_service) -> None:
    memory = mcp_service.settings.memory_database_path
    settings = replace(mcp_service.settings, multi_agent=True)
    app = build_agent(settings, model=RoleModel(), checkpointer=create_checkpointer(memory))
    chat = ChatService(app, ConversationStore(memory))
    before = mcp_service.ticket_count()
    thread_id = chat.start_conversation("E104")

    turn = chat.send(thread_id, "E104", "My VPN isn't connecting, please raise a ticket.")

    assert turn["pending_approval"] is True
    assert mcp_service.ticket_count() == before
    assert chat.pending_approval(thread_id, "E104")["args"] == DRAFT

    done = chat.resume(thread_id, "E104", "approve")

    assert mcp_service.ticket_count() == before + 1
    assert done["answer"].startswith("Done:")
