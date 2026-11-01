"""Prompt templates are discoverable and render over the real server."""

import asyncio
import re

import httpx
import pytest
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamablehttp_client

from conftest import make_token

EXPECTED_PROMPTS = {
    "raise_it_ticket",
    "request_leave",
    "summarize_my_tickets",
    "leave_overview",
}


def with_session(server_url: str, action):
    async def run():
        headers = {"Authorization": f"Bearer {make_token('E104')}"}
        async with streamablehttp_client(server_url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await action(session)

    return asyncio.run(run())


def prompt_text(server_url: str, name: str, arguments: dict[str, str] | None = None) -> str:
    result = with_session(server_url, lambda session: session.get_prompt(name, arguments))
    assert len(result.messages) == 1
    assert result.messages[0].role == "user"
    return result.messages[0].content.text


def prompt_error(server_url: str, name: str, arguments: dict[str, str] | None = None) -> str:
    # Caught inside the session: escaping the client's task group would wrap it in an ExceptionGroup.
    async def action(session):
        with pytest.raises(McpError) as caught:
            await session.get_prompt(name, arguments)
        return str(caught.value)

    return with_session(server_url, action)


def test_server_lists_prompts_with_their_arguments(server_url: str) -> None:
    prompts = with_session(server_url, lambda session: session.list_prompts()).prompts
    arguments = {p.name: {a.name: a.required for a in p.arguments or []} for p in prompts}

    assert arguments == {
        "raise_it_ticket": {"issue": True, "category": False},
        "request_leave": {"leave_type": True, "when": True, "reason": False},
        "summarize_my_tickets": {},
        "leave_overview": {},
    }
    assert all(p.title and p.description for p in prompts)


def test_raise_it_ticket_prompt_points_at_create_ticket(server_url: str) -> None:
    text = prompt_text(
        server_url,
        "raise_it_ticket",
        {"issue": "VPN drops every ten minutes", "category": "VPN"},
    )

    assert "Employee problem: VPN drops every ten minutes" in text
    assert "Category: VPN" in text
    assert "create_ticket" in text


def test_raise_it_ticket_prompt_category_is_optional(server_url: str) -> None:
    text = prompt_text(server_url, "raise_it_ticket", {"issue": "Printer is jammed"})

    assert "Category: not given" in text


def test_request_leave_prompt_includes_arguments_and_todays_date(server_url: str) -> None:
    text = prompt_text(
        server_url,
        "request_leave",
        {"leave_type": "annual", "when": "next Friday", "reason": "Family event"},
    )

    assert "annual leave: next Friday" in text
    assert "Reason: Family event" in text
    assert re.search(r"Today's date: \d{4}-\d{2}-\d{2}", text)
    assert "check_leave_balance" in text
    assert "apply_leave" in text


@pytest.mark.parametrize(
    ("name", "tools"),
    [
        ("summarize_my_tickets", ["list_my_tickets"]),
        ("leave_overview", ["check_leave_balance", "get_leave_history"]),
    ],
)
def test_read_only_prompts_name_the_tools_to_call(
    server_url: str, name: str, tools: list[str]
) -> None:
    text = prompt_text(server_url, name)

    assert all(tool in text for tool in tools)


def test_prompt_rejects_an_invalid_argument(server_url: str) -> None:
    error = prompt_error(
        server_url, "request_leave", {"leave_type": "bogus", "when": "next Friday"}
    )

    assert "leave_type" in error


def test_prompt_requires_its_mandatory_arguments(server_url: str) -> None:
    error = prompt_error(server_url, "raise_it_ticket")

    assert "Missing required arguments" in error
    assert "issue" in error


def test_prompts_require_a_token(server_url: str) -> None:
    response = httpx.post(server_url, json={"jsonrpc": "2.0", "id": 1, "method": "prompts/list"})

    assert response.status_code == 401
