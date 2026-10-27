import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from agents.agent import build_agent
from build_database import build_database
from config import Settings
from data.repository import HelpdeskRepository
from domain import HelpdeskContext
from tools.helpdesk import create_helpdesk_tools


class _OneToolModel:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"name": "get_ticket_status", "args": {"ticket_id": "INC-1042"}, "id": "t1", "type": "tool_call"}],
            )
        return AIMessage(content="done")


def test_tools_do_not_accept_model_selected_employee_identity(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    tools = {item.name: item for item in create_helpdesk_tools(HelpdeskRepository(database))}

    assert set(tools) == {
        "get_ticket_status",
        "list_my_tickets",
        "check_leave_balance",
        "create_ticket",
        "get_leave_history",
        "apply_leave",
    }
    assert "employee_id" not in tools["apply_leave"].args
    assert "employee_id" not in tools["create_ticket"].args
    assert "employee_id" not in tools["check_leave_balance"].args
    assert "employee_id" not in tools["list_my_tickets"].args
    assert "runtime" not in tools["get_ticket_status"].tool_call_schema.model_json_schema()["properties"]


def test_ticket_tool_uses_identity_from_runtime_context(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    app = build_agent(
        Settings(database, "E104", "test-model", 4),
        HelpdeskRepository(database),
        model=_OneToolModel(),
    )

    result = app.invoke(
        {"messages": [HumanMessage(content="status?")]},
        context=HelpdeskContext(employee_id="E104"),
    )

    payload = json.loads(result["messages"][-2].content)
    assert payload["found"] is True
    assert payload["priority"] == "high"
