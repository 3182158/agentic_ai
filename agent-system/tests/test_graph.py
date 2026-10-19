from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from config import Settings
from data.repository import HelpdeskRepository
from graph.agent import build_agent
from build_database import build_database


class FakeToolCallingModel:
    """Tiny deterministic chat-model double; no network or API key required."""

    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools):
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


def test_graph_executes_tool_and_returns_model_answer(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    model = FakeToolCallingModel()
    settings = Settings(database, "E104", "test-model", 4)
    app = build_agent(settings, HelpdeskRepository(database), model=model)

    result = app.invoke({"messages": [HumanMessage(content="What is the status of INC-1042?")], "model_steps": 0})

    assert result["messages"][-1].content == "INC-1042 is in progress with high priority."
    assert model.calls == 2
    assert any(getattr(message, "name", None) == "get_ticket_status" for message in result["messages"])


def test_graph_stops_after_model_step_limit(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    model = FakeToolCallingModel()
    settings = Settings(database, "E104", "test-model", 1)
    app = build_agent(settings, HelpdeskRepository(database), model=model)

    result = app.invoke({"messages": [HumanMessage(content="Look up a ticket")], "model_steps": 0})

    assert "reached the limit" in result["messages"][-1].content
    assert model.calls == 1
