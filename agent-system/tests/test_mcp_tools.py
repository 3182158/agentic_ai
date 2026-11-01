"""Agent tools discovered from the real MCP service running on a local port."""

import asyncio
import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.agent import build_agent
from config import Settings
from domain import HelpdeskContext
from memory.service import content_as_text
from ticket_leave_mcp import server as service_module
from ticket_leave_mcp.config import Settings as ServiceSettings
from tools.mcp_client import McpSetupError, load_helpdesk_tools

DRAFT = {
    "title": "VPN not connecting",
    "description": "The VPN fails to connect from home.",
    "category": "VPN",
    "priority": "medium",
}


class _ScriptedModel:
    """Requests one tool call, then answers once it sees the tool's result."""

    def __init__(self, tool_name: str, args: dict) -> None:
        self.tool_name, self.args = tool_name, args

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="done")
        call = {"name": self.tool_name, "args": self.args, "id": "t1", "type": "tool_call"}
        return AIMessage(content="", tool_calls=[call])


def _agent(settings: Settings, tool_name: str, args: dict, **kwargs):
    return build_agent(settings, model=_ScriptedModel(tool_name, args), **kwargs)


class _ParallelModel(_ScriptedModel):
    """Requests two read tools in one model turn."""

    def invoke(self, messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="done")
        calls = [
            {"name": "list_my_tickets", "args": {}, "id": "p1", "type": "tool_call"},
            {"name": "check_leave_balance", "args": {}, "id": "p2", "type": "tool_call"},
        ]
        return AIMessage(content="", tool_calls=calls)


def _context(employee_id: str) -> HelpdeskContext:
    return HelpdeskContext(employee_id=employee_id)


def _tool_message(app, employee_id: str = "E104") -> ToolMessage:
    result = app.invoke({"messages": [HumanMessage(content="go")]}, context=_context(employee_id))
    return next(m for m in reversed(result["messages"]) if isinstance(m, ToolMessage))


def _payload(message: ToolMessage) -> dict:
    return json.loads(content_as_text(message.content))


def _run_approved_write(app, thread_id: str) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    paused = app.invoke(
        {"messages": [HumanMessage(content="go")]}, config, context=_context("E104")
    )
    assert paused["__interrupt__"]
    app.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config, context=_context("E104"))


def test_tools_mirror_the_servers_definitions(mcp_service) -> None:
    settings = mcp_service.settings
    server = service_module.create_server(ServiceSettings(mcp_service.database, settings.mcp_secret))
    declared = asyncio.run(server.list_tools())
    loaded = {t.name: t for t in load_helpdesk_tools(settings.mcp_url, settings.mcp_secret)}

    assert set(loaded) == {t.name for t in declared} and len(loaded) == 6
    for server_tool in declared:
        assert loaded[server_tool.name].description == server_tool.description
        assert loaded[server_tool.name].args_schema == server_tool.inputSchema
        assert "employee_id" not in server_tool.inputSchema.get("properties", {})


def test_new_server_tool_needs_no_agent_change(start_mcp_service, monkeypatch) -> None:
    original = service_module.create_server

    def with_new_tool(settings, repository=None):
        mcp = original(settings, repository)

        @mcp.tool()
        def get_it_contact() -> str:
            """Return the IT service desk contact details."""
            return "it-desk@acme.example"

        return mcp

    monkeypatch.setattr(service_module, "create_server", with_new_tool)
    message = _tool_message(_agent(start_mcp_service().settings, "get_it_contact", {}))

    assert message.status == "success"
    assert "it-desk@acme.example" in content_as_text(message.content)


def test_agent_reads_ticket_through_mcp(mcp_service) -> None:
    message = _tool_message(
        _agent(mcp_service.settings, "get_ticket_status", {"ticket_id": "INC-1042"})
    )

    assert message.status == "success"
    assert _payload(message)["found"] is True
    assert _payload(message)["priority"] == "high"


def test_mcp_enforces_identity_from_agent_context(mcp_service) -> None:
    app = _agent(mcp_service.settings, "get_ticket_status", {"ticket_id": "INC-1043"})

    assert _payload(_tool_message(app, "E104"))["found"] is False
    assert _payload(_tool_message(app, "E105"))["found"] is True


def test_parallel_tool_calls_each_reach_the_server_as_the_employee(mcp_service) -> None:
    app = build_agent(mcp_service.settings, model=_ParallelModel("", {}))

    result = app.invoke({"messages": [HumanMessage(content="go")]}, context=_context("E104"))

    replies = {m.name: m for m in result["messages"] if isinstance(m, ToolMessage)}
    assert set(replies) == {"list_my_tickets", "check_leave_balance"}
    assert all(m.status == "success" for m in replies.values())
    assert _payload(replies["check_leave_balance"])["employee_id"] == "E104"


def test_server_validation_errors_reach_the_model(mcp_service) -> None:
    app = _agent(mcp_service.settings, "get_ticket_status", {})

    message = _tool_message(app)

    assert message.status == "error"


def test_write_through_mcp_waits_for_approval(mcp_service) -> None:
    before = mcp_service.ticket_count()
    app = _agent(mcp_service.settings, "create_ticket", DRAFT, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "a"}}

    paused = app.invoke({"messages": [HumanMessage(content="go")]}, config, context=_context("E104"))

    assert paused["__interrupt__"]
    assert mcp_service.ticket_count() == before

    done = app.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}), config, context=_context("E104")
    )

    assert mcp_service.ticket_count() == before + 1
    assert _payload(next(m for m in done["messages"] if isinstance(m, ToolMessage)))["created"]


def test_repeating_an_approved_write_cannot_double_create(mcp_service) -> None:
    before = mcp_service.ticket_count()
    app = _agent(mcp_service.settings, "create_ticket", DRAFT, checkpointer=InMemorySaver())

    _run_approved_write(app, "first")
    _run_approved_write(app, "second")

    assert mcp_service.ticket_count() == before + 1


def test_service_going_down_is_reported_as_a_tool_error(mcp_service) -> None:
    app = _agent(mcp_service.settings, "list_my_tickets", {})
    mcp_service.stop()

    message = _tool_message(app)

    assert message.status == "error"
    assert "unavailable" in content_as_text(message.content)


def test_unreachable_service_at_startup_fails_clearly(mcp_service) -> None:
    down = replace(mcp_service.settings, mcp_url="http://127.0.0.1:9/mcp")

    with pytest.raises(McpSetupError, match="helpdesk MCP server"):
        _agent(down, "list_my_tickets", {})


def test_missing_secret_is_reported_before_connecting(mcp_service) -> None:
    with pytest.raises(McpSetupError, match="HELPDESK_MCP_SECRET"):
        _agent(replace(mcp_service.settings, mcp_secret=""), "list_my_tickets", {})
