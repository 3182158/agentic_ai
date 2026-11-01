from dataclasses import replace

from langchain_core.messages import AIMessage, HumanMessage

from domain import HelpdeskContext
from agents.agent import build_agent
from memory.checkpointer import create_checkpointer
from memory.service import ChatService, content_as_text
from memory.store import ConversationStore


class FakeToolCallingModel:
    """Tiny deterministic chat-model double; no network or API key required."""

    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools, **kwargs):
        del kwargs
        self.tools = tools
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_ticket_status",
                        "args": {"ticket_id": "INC-1042"},
                        "id": "tool-call-1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="INC-1042 is in progress with high priority.")


class RepeatingToolCallingModel:
    """Request one tool repeatedly to exercise independent per-tool budgets."""

    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools, **kwargs):
        del kwargs
        self.tools = tools
        return self

    def invoke(self, messages):
        del messages
        self.calls += 1
        if self.calls <= 3 or self.calls == 4:
            tool_name = "get_ticket_status" if self.calls <= 3 else "list_my_tickets"
            args = {"ticket_id": "INC-1042"} if self.calls <= 3 else {}
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": tool_name,
                        "args": args,
                        "id": f"tool-call-{self.calls}",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="Finished the lookups.")


def test_graph_executes_tool_and_returns_model_answer(mcp_service) -> None:
    model = FakeToolCallingModel()
    app = build_agent(mcp_service.settings, model=model)

    result = app.invoke(
        {"messages": [HumanMessage(content="What is the status of INC-1042?")]},
        context=HelpdeskContext(employee_id="E104"),
    )

    assert result["messages"][-1].content == "INC-1042 is in progress with high priority."
    assert model.calls == 2
    assert any(getattr(message, "name", None) == "get_ticket_status" for message in result["messages"])


def test_graph_stops_after_model_step_limit(mcp_service) -> None:
    model = FakeToolCallingModel()
    app = build_agent(replace(mcp_service.settings, max_model_steps=1), model=model)

    result = app.invoke(
        {"messages": [HumanMessage(content="Look up a ticket")]},
        context=HelpdeskContext(employee_id="E104"),
    )

    assert "Model call limits exceeded" in result["messages"][-1].content
    assert model.calls == 1


def test_tool_run_limit_is_scoped_to_each_tool(mcp_service) -> None:
    app = build_agent(
        replace(mcp_service.settings, max_model_steps=6),
        model=RepeatingToolCallingModel(),
    )

    result = app.invoke(
        {"messages": [HumanMessage(content="Look up my helpdesk data")]},
        context=HelpdeskContext(employee_id="E104"),
    )
    tool_results = [message for message in result["messages"] if getattr(message, "name", None)]

    assert [message.name for message in tool_results] == [
        "get_ticket_status",
        "get_ticket_status",
        "get_ticket_status",
        "list_my_tickets",
    ]
    assert "limit" in content_as_text(tool_results[2].content).casefold()
    assert "limit" not in content_as_text(tool_results[3].content).casefold()


def test_checkpointer_keeps_agent_state_per_thread(mcp_service) -> None:
    memory = mcp_service.settings.memory_database_path
    app = build_agent(
        mcp_service.settings,
        model=FakeToolCallingModel(),
        checkpointer=create_checkpointer(memory),
    )
    chat = ChatService(app, ConversationStore(memory))
    thread_id = chat.start_conversation("E104")

    turn = chat.send(thread_id, "E104", "What is the status of INC-1042?")

    assert "in progress" in turn["answer"]
    assert turn["tool_names"] == ["get_ticket_status"]
    state = app.get_state({"configurable": {"thread_id": thread_id}}).values["messages"]
    assert any(getattr(m, "name", None) == "get_ticket_status" for m in state)
    assert len([m for m in state if isinstance(m, HumanMessage)]) == 1

    chat.send(thread_id, "E104", "What about its priority?")
    state = app.get_state({"configurable": {"thread_id": thread_id}}).values["messages"]
    assert len([m for m in state if isinstance(m, HumanMessage)]) == 2

    # Display transcript holds only clean user/assistant text, no tool messages.
    transcript = chat.store.get_messages(thread_id, "E104")
    assert [m["role"] for m in transcript] == ["user", "assistant"] * 2
