"""Prompt templates come from the real MCP service and render into model input."""

import asyncio

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from mcp.types import Prompt

from agents.agent import build_agent
from domain import HelpdeskContext
from ticket_leave_mcp import server as service_module
from ticket_leave_mcp.config import Settings as ServiceSettings
from tools.mcp_client import (
    McpPromptError,
    _FreshToken,
    get_helpdesk_prompt,
    list_helpdesk_prompts,
    prompt_label,
)


def _connection(running) -> tuple[str, str]:
    return running.settings.mcp_url, running.settings.mcp_secret


def test_prompts_mirror_the_servers_definitions(mcp_service) -> None:
    url, secret = _connection(mcp_service)
    server = service_module.create_server(ServiceSettings(mcp_service.database, secret))
    declared = {p.name: p for p in asyncio.run(server.list_prompts())}
    loaded = {p.name: p for p in list_helpdesk_prompts(url, secret)}

    assert loaded.keys() == declared.keys() and len(loaded) == 4
    for name, prompt in loaded.items():
        assert prompt.title == declared[name].title
        assert prompt.description == declared[name].description
        assert prompt.arguments == declared[name].arguments
        assert "employee_id" not in {a.name for a in prompt.arguments or []}


def test_new_server_prompt_needs_no_app_change(start_mcp_service, monkeypatch) -> None:
    original = service_module.create_server

    def with_new_prompt(settings, repository=None):
        mcp = original(settings, repository)

        @mcp.prompt(title="Reset my password")
        def reset_password() -> str:
            """Guide a password reset."""
            return "Explain the self-service portal steps for resetting a password."

        return mcp

    monkeypatch.setattr(service_module, "create_server", with_new_prompt)
    url, secret = _connection(start_mcp_service())

    assert "reset_password" in {p.name for p in list_helpdesk_prompts(url, secret)}
    assert "self-service portal" in get_helpdesk_prompt(url, secret, "reset_password")


def test_get_prompt_renders_the_text_for_the_model(mcp_service) -> None:
    url, secret = _connection(mcp_service)

    text = get_helpdesk_prompt(
        url, secret, "raise_it_ticket", {"issue": "VPN drops", "category": "VPN"}
    )

    assert "Employee problem: VPN drops" in text
    assert "Category: VPN" in text
    assert "create_ticket" in text


def test_get_prompt_without_arguments(mcp_service) -> None:
    url, secret = _connection(mcp_service)

    assert "list_my_tickets" in get_helpdesk_prompt(url, secret, "summarize_my_tickets")


@pytest.mark.parametrize(
    "name, arguments, explained",
    [
        ("request_leave", {"leave_type": "bogus", "when": "tomorrow"}, "leave_type"),
        ("raise_it_ticket", {}, "Missing required arguments"),
        ("no_such_prompt", {}, "Unknown prompt"),
    ],
)
def test_server_rejections_are_explained(mcp_service, name, arguments, explained) -> None:
    url, secret = _connection(mcp_service)

    with pytest.raises(McpPromptError, match=explained):
        get_helpdesk_prompt(url, secret, name, arguments)


def test_unreachable_service_is_reported(mcp_service) -> None:
    secret = mcp_service.settings.mcp_secret

    with pytest.raises(McpPromptError, match="Cannot list prompts.*127.0.0.1:9"):
        list_helpdesk_prompts("http://127.0.0.1:9/mcp", secret)


def test_wrong_secret_is_reported(mcp_service) -> None:
    with pytest.raises(McpPromptError, match="401"):
        list_helpdesk_prompts(mcp_service.settings.mcp_url, "x" * 40)


def test_each_request_is_signed_when_it_is_sent(monkeypatch) -> None:
    tokens = iter(["first", "second"])
    subjects = []

    def sign(subject, secret):
        subjects.append(subject)
        return next(tokens)

    monkeypatch.setattr("tools.mcp_client._token", sign)
    auth = _FreshToken("secret", "helpdesk-agent")

    sent = []
    for _ in range(2):
        request = httpx.Request("POST", "http://127.0.0.1/mcp")
        next(auth.auth_flow(request))
        sent.append(request.headers["Authorization"])

    assert sent == ["Bearer first", "Bearer second"]
    assert subjects == ["helpdesk-agent", "helpdesk-agent"]


def test_prompt_label_shows_the_title_and_the_values_given() -> None:
    leave = Prompt(name="request_leave", title="Request leave")

    assert prompt_label(leave, {"leave_type": "annual", "when": "Friday"}) == (
        "Request leave: leave_type=annual, when=Friday"
    )
    assert prompt_label(Prompt(name="leave_overview"), {}) == "leave_overview"


class _CreateTicketModel:
    """Remembers what it is shown, then asks for a ticket to be created."""

    def __init__(self) -> None:
        self.seen: list[list] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.seen.append(messages)
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="done")
        args = {
            "title": "VPN drops",
            "description": "The VPN drops every ten minutes.",
            "category": "VPN",
            "priority": "medium",
        }
        return AIMessage(
            content="", tool_calls=[{"name": "create_ticket", "args": args, "id": "t1", "type": "tool_call"}]
        )


def test_a_templated_write_still_waits_for_approval(mcp_service) -> None:
    url, secret = _connection(mcp_service)
    text = get_helpdesk_prompt(url, secret, "raise_it_ticket", {"issue": "VPN drops"})
    model = _CreateTicketModel()
    app = build_agent(mcp_service.settings, model=model, checkpointer=InMemorySaver())
    before = mcp_service.ticket_count()

    paused = app.invoke(
        {"messages": [HumanMessage(content=text)]},
        {"configurable": {"thread_id": "t"}},
        context=HelpdeskContext(employee_id="E104"),
    )

    shown = [m.content for m in model.seen[0] if isinstance(m, HumanMessage)]
    assert shown == [text]
    assert paused["__interrupt__"]
    assert mcp_service.ticket_count() == before
