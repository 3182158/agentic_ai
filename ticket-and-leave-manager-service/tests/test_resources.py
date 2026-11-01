"""The employee profile resource is discoverable and always belongs to the caller."""

import asyncio
import json

import httpx
import pytest
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamablehttp_client

from conftest import make_token

PROFILE_URI = "employee://me/profile"


def with_session(server_url: str, action, subject: str = "E104"):
    async def run():
        headers = {"Authorization": f"Bearer {make_token(subject)}"}
        async with streamablehttp_client(server_url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await action(session)

    return asyncio.run(run())


def read_profile(server_url: str, subject: str = "E104") -> dict:
    result = with_session(server_url, lambda session: session.read_resource(PROFILE_URI), subject)
    assert len(result.contents) == 1
    assert result.contents[0].mimeType == "application/json"
    return json.loads(result.contents[0].text)


def read_error(server_url: str, uri: str, subject: str = "E104") -> str:
    # Caught inside the session: escaping the client's task group would wrap it in an ExceptionGroup.
    async def action(session):
        with pytest.raises(McpError) as caught:
            await session.read_resource(uri)
        return str(caught.value)

    return with_session(server_url, action, subject)


def test_server_lists_only_the_profile_resource(server_url: str) -> None:
    resources = with_session(server_url, lambda session: session.list_resources()).resources

    assert [str(resource.uri) for resource in resources] == [PROFILE_URI]
    assert all(r.title and r.description and r.mimeType == "application/json" for r in resources)


def test_server_defines_no_resource_template(server_url: str) -> None:
    # A template like employee://{employee_id}/profile would let a caller choose whose data to
    # read, and FastMCP silently registers a resource function that has parameters as a template.
    result = with_session(server_url, lambda session: session.list_resource_templates())

    assert result.resourceTemplates == []


@pytest.mark.parametrize(
    ("employee_id", "full_name", "department", "office_location", "manager_name"),
    [
        ("E104", "Asha Raman", "Engineering", "Seattle", "Meera Patel"),
        ("E105", "Luis Gomez", "Sales", "Austin", "Meera Patel"),
        ("E101", "Ravi Shah", "Technology", "Seattle", None),
    ],
)
def test_profile_is_the_signed_in_employees_and_nothing_more(
    server_url: str,
    employee_id: str,
    full_name: str,
    department: str,
    office_location: str,
    manager_name: str | None,
) -> None:
    assert read_profile(server_url, employee_id) == {
        "employee_id": employee_id,
        "full_name": full_name,
        "department": department,
        "office_location": office_location,
        "manager_name": manager_name,
    }


def test_another_employees_profile_cannot_be_requested_by_uri(server_url: str) -> None:
    error = read_error(server_url, "employee://E105/profile")

    assert "Unknown resource" in error


def test_profile_of_a_non_employee_identity_is_an_error(server_url: str) -> None:
    error = read_error(server_url, PROFILE_URI, subject="helpdesk-agent")

    assert "No active employee for this token" in error


@pytest.mark.parametrize("method", ["resources/list", "resources/templates/list", "resources/read"])
def test_resources_require_a_token(server_url: str, method: str) -> None:
    request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {"uri": PROFILE_URI}}

    assert httpx.post(server_url, json=request).status_code == 401
