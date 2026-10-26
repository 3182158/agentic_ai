from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from config import Settings
from data.repository import HelpdeskRepository
from agents.agent import build_agent
from streamlit_app import _run_turn
from build_database import build_database


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


def test_graph_executes_tool_and_returns_model_answer(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    model = FakeToolCallingModel()
    settings = Settings(database, "E104", "test-model", 4)
    app = build_agent(settings, HelpdeskRepository(database), model=model)

    result = app.invoke({"messages": [HumanMessage(content="What is the status of INC-1042?")]})

    assert result["messages"][-1].content == "INC-1042 is in progress with high priority."
    assert model.calls == 2
    assert any(getattr(message, "name", None) == "get_ticket_status" for message in result["messages"])


def test_graph_stops_after_model_step_limit(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    model = FakeToolCallingModel()
    settings = Settings(database, "E104", "test-model", 1)
    app = build_agent(settings, HelpdeskRepository(database), model=model)

    result = app.invoke({"messages": [HumanMessage(content="Look up a ticket")]})

    assert "Model call limits exceeded" in result["messages"][-1].content
    assert model.calls == 1


def test_tool_run_limit_is_scoped_to_each_tool(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    settings = Settings(database, "E104", "test-model", 6)
    app = build_agent(
        settings,
        HelpdeskRepository(database),
        model=RepeatingToolCallingModel(),
    )

    result = app.invoke({"messages": [HumanMessage(content="Look up my helpdesk data")]})
    tool_results = [message for message in result["messages"] if getattr(message, "name", None)]

    assert [message.name for message in tool_results] == [
        "get_ticket_status",
        "get_ticket_status",
        "get_ticket_status",
        "list_my_tickets",
    ]
    assert "limit" in tool_results[2].content.casefold()
    assert "limit" not in tool_results[3].content.casefold()


def test_streamlit_turn_preserves_tool_messages_and_followup_context(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    app = build_agent(
        Settings(database, "E104", "test-model", 4),
        HelpdeskRepository(database),
        model=FakeToolCallingModel(),
    )
    answer, messages = _run_turn(app, [], "What is the status of INC-1042?")

    assert "in progress" in answer
    assert any(getattr(message, "name", None) == "get_ticket_status" for message in messages)
    assert len([message for message in messages if isinstance(message, HumanMessage)]) == 1

    _, followup_messages = _run_turn(app, messages, "What about its priority?")

    assert followup_messages[:len(messages)] == messages
    assert len([message for message in followup_messages if isinstance(message, HumanMessage)]) == 2
