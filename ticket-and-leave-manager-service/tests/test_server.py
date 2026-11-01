import json

import httpx
import pytest

from conftest import SECRET, make_token
from ticket_leave_mcp.auth import AuthError, employee_id_from_headers

EXPECTED_TOOLS = {
    "get_ticket_status",
    "list_my_tickets",
    "check_leave_balance",
    "create_ticket",
    "get_leave_history",
    "apply_leave",
}


def auth(employee_id: str = "E104", **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(employee_id)}", **extra}


def payload(result) -> dict:
    if result.structuredContent:
        return result.structuredContent
    return json.loads(result.content[0].text)


def test_token_validation_rejects_bad_tokens() -> None:
    with pytest.raises(AuthError):
        employee_id_from_headers({}, SECRET)
    with pytest.raises(AuthError):
        employee_id_from_headers({"authorization": f"Bearer {make_token('E104', secret='x' * 40)}"}, SECRET)
    with pytest.raises(AuthError):
        employee_id_from_headers(
            {"authorization": f"Bearer {make_token('E104', expires_in=-10)}"}, SECRET
        )
    assert employee_id_from_headers({"authorization": f"Bearer {make_token('e104')}"}, SECRET) == "E104"


def test_server_lists_all_six_tools(server_url: str) -> None:
    import asyncio

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def run():
        async with streamablehttp_client(server_url, headers=auth()) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.list_tools()

    tools = asyncio.run(run()).tools
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_read_tool_uses_identity_from_token(call_tool) -> None:
    result = call_tool("list_my_tickets", headers=auth("E104"))

    assert not result.isError
    assert {t["ticket_id"] for t in payload(result)["tickets"]} == {
        "INC-1042", "INC-1050", "INC-1058"
    }


def test_other_employees_ticket_is_blocked(call_tool) -> None:
    result = call_tool("get_ticket_status", {"ticket_id": "INC-1043"}, headers=auth("E104"))

    assert payload(result)["found"] is False


def test_request_without_token_is_rejected(server_url: str) -> None:
    response = httpx.post(server_url, json={})

    assert response.status_code == 401


def test_request_with_bad_token_is_rejected(server_url: str) -> None:
    bad = {"Authorization": f"Bearer {make_token('E104', secret='x' * 40)}"}

    assert httpx.post(server_url, json={}, headers=bad).status_code == 401


def test_write_requires_idempotency_key(call_tool) -> None:
    args = {
        "title": "VPN keeps dropping",
        "description": "VPN drops every ten minutes.",
        "category": "VPN",
        "priority": "medium",
    }
    assert call_tool("create_ticket", args, headers=auth()).isError


def test_create_ticket_is_idempotent_over_http(call_tool) -> None:
    args = {
        "title": "VPN keeps dropping",
        "description": "VPN drops every ten minutes.",
        "category": "VPN",
        "priority": "medium",
    }
    headers = auth(**{"Idempotency-Key": "create_ticket:call-1"})
    first = payload(call_tool("create_ticket", args, headers=headers))
    second = payload(call_tool("create_ticket", args, headers=headers))

    assert first["created"] is True
    assert second["created"] is False
    assert second["ticket_id"] == first["ticket_id"]
