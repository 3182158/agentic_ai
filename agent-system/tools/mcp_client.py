"""Helpdesk tools, prompts and the employee profile loaded straight from the ticket-and-leave MCP server."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterator
from typing import Any, cast

import httpx
import jwt
from langchain.tools import ToolRuntime
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, ToolCallInterceptor
from mcp import McpError
from mcp.types import CallToolResult, Prompt, TextContent

from domain import EmployeeProfile, HelpdeskContext

logger = logging.getLogger(__name__)

TOKEN_TTL_SECONDS = 60
SERVICE_SUBJECT = "helpdesk-agent"
PROFILE_URI = "employee://me/profile"
PROFILE_TTL_SECONDS = 300
PROFILE_RETRY_SECONDS = 30


class McpSetupError(RuntimeError):
    """The helpdesk MCP server is not configured or cannot be reached."""


class McpPromptError(RuntimeError):
    """A prompt template could not be listed or rendered."""


class McpProfileError(RuntimeError):
    """The employee profile could not be read."""


def _token(subject: str, secret: str) -> str:
    claims = {"sub": subject, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(claims, secret, algorithm="HS256")


class _FreshToken(httpx.Auth):
    """Signs each request as `subject` when it is sent, so a long-running app never sends an expired token."""

    def __init__(self, secret: str, subject: str) -> None:
        self.secret = secret
        self.subject = subject

    def auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
        request.headers["Authorization"] = f"Bearer {_token(self.subject, self.secret)}"
        yield request


def _unwrap(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup):  # anyio wraps transport errors in a task group
        exc = exc.exceptions[0]
    return exc


def _reason(exc: BaseException) -> str:
    exc = _unwrap(exc)
    return f"{type(exc).__name__}: {exc}".splitlines()[0]


def _server_error(exc: BaseException | None) -> McpError | None:
    """The server's own error behind `exc`; the adapters wrap it when they read resources."""
    while exc is not None:
        exc = _unwrap(exc)
        if isinstance(exc, McpError):
            return exc
        exc = exc.__cause__
    return None


def _failure(exc: BaseException) -> str:
    """One readable line for a failed request; a server error keeps the server's own text."""
    server_error = _server_error(exc)
    if server_error is None:
        return _reason(exc)
    lines = (line.strip() for line in str(server_error).splitlines())
    return " ".join(
        line for line in lines if line and not line.startswith("For further information")
    )


def _act_as_signed_in_employee(secret: str) -> ToolCallInterceptor:
    """Interceptor: each call carries the application's employee identity, never a model-chosen one."""

    async def interceptor(request: MCPToolCallRequest, handler):
        runtime = cast("ToolRuntime[HelpdeskContext] | None", request.runtime)
        if runtime is None:
            raise RuntimeError("Helpdesk MCP tools can only run inside the agent.")
        headers = {
            "Authorization": f"Bearer {_token(runtime.context.employee_id, secret)}",
            # tool_call_id is stable across the approval resume, so a repeat cannot double-write.
            "Idempotency-Key": f"{request.name}:{runtime.tool_call_id}",
        }
        try:
            return await handler(request.override(headers=headers))
        except Exception as exc:
            # An unreachable service must not abort the run and strand the thread mid-tool-call.
            message = f"Helpdesk service unavailable: {_reason(exc)}"
            return CallToolResult(isError=True, content=[TextContent(type="text", text=message)])

    return interceptor


def _allow_sync_calls(tool: BaseTool) -> BaseTool:
    """Adapter tools are async-only, but this app drives the agent synchronously."""
    if not isinstance(tool, StructuredTool) or tool.func or not tool.coroutine:
        return tool
    call = tool.coroutine

    # The parameter must be named `runtime` so LangGraph keeps injecting it.
    def run(runtime: ToolRuntime, **arguments: Any) -> Any:
        return asyncio.run(call(runtime=runtime, **arguments))

    tool.func = run
    return tool


def load_helpdesk_tools(url: str, secret: str) -> list[BaseTool]:
    """Discover the server's tools; their names, descriptions and schemas come from the server."""
    if not secret:
        raise McpSetupError("HELPDESK_MCP_SECRET is not set. It must match the MCP service's secret.")
    client = MultiServerMCPClient(
        {
            "helpdesk": {
                "transport": "streamable_http",
                "url": url,
                # Discovery is not an employee action, so it uses a service identity.
                "headers": {"Authorization": f"Bearer {_token(SERVICE_SUBJECT, secret)}"},
            }
        },
        tool_interceptors=[_act_as_signed_in_employee(secret)],
    )
    try:
        tools = asyncio.run(client.get_tools())
    except Exception as exc:
        raise McpSetupError(
            f"Cannot load tools from the helpdesk MCP server at {url} ({_reason(exc)}). "
            "Check that it is running and that HELPDESK_MCP_SECRET matches its secret."
        ) from exc
    return [_allow_sync_calls(tool) for tool in tools]


def _prompt_client(url: str, secret: str) -> MultiServerMCPClient:
    # Prompts are fetched long after startup, so a fixed token would have expired by then.
    return MultiServerMCPClient(
        {
            "helpdesk": {
                "transport": "streamable_http",
                "url": url,
                "auth": _FreshToken(secret, SERVICE_SUBJECT),
            }
        }
    )


def list_helpdesk_prompts(url: str, secret: str) -> list[Prompt]:
    """List the server's prompt templates; names, titles and arguments come from the server."""

    async def fetch() -> list[Prompt]:
        async with _prompt_client(url, secret).session("helpdesk") as session:
            return (await session.list_prompts()).prompts

    try:
        return asyncio.run(fetch())
    except Exception as exc:
        raise McpPromptError(
            f"Cannot list prompts from the helpdesk MCP server at {url} ({_failure(exc)})."
        ) from exc


def get_helpdesk_prompt(
    url: str, secret: str, name: str, arguments: dict[str, str] | None = None
) -> str:
    """Render a prompt template into the text sent to the model as the user's message."""
    try:
        messages = asyncio.run(
            _prompt_client(url, secret).get_prompt("helpdesk", name, arguments=arguments)
        )
    except Exception as exc:
        raise McpPromptError(f"Cannot get prompt '{name}' ({_failure(exc)}).") from exc
    if not messages or not all(
        isinstance(m, HumanMessage) and isinstance(m.content, str) for m in messages
    ):
        raise McpPromptError(f"Prompt '{name}' did not return plain user text.")
    return "\n\n".join(m.content for m in messages)


def prompt_label(prompt: Prompt, arguments: dict[str, str]) -> str:
    """Short transcript text for a template run: its title and the values it was given."""
    title = prompt.title or prompt.name
    given = ", ".join(f"{key}={value}" for key, value in arguments.items())
    return f"{title}: {given}" if given else title


def read_employee_profile(url: str, secret: str, employee_id: str) -> EmployeeProfile:
    """Read the employee's directory profile (an MCP resource).

    The server returns the profile of whoever the token names, so this signs as the employee;
    the service identity used for discovery and prompts is refused.
    """
    client = MultiServerMCPClient(
        {
            "helpdesk": {
                "transport": "streamable_http",
                "url": url,
                "auth": _FreshToken(secret, employee_id),
            }
        }
    )
    try:
        blobs = asyncio.run(client.get_resources("helpdesk", uris=PROFILE_URI))
        return EmployeeProfile.model_validate_json(blobs[0].as_string())
    except Exception as exc:
        raise McpProfileError(f"Cannot read the employee profile ({_failure(exc)}).") from exc


class EmployeeProfiles:
    """Each employee's profile, read as that employee and kept for a few minutes.

    A profile is optional context, so a failed read gives None rather than an error, and is
    retried only after a short pause instead of on every model call.
    """

    def __init__(
        self, url: str, secret: str, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.url = url
        self.secret = secret
        self._clock = clock
        self._entries: dict[str, tuple[float, EmployeeProfile | None]] = {}

    def get(self, employee_id: str) -> EmployeeProfile | None:
        entry = self._entries.get(employee_id)
        if entry and self._clock() < entry[0]:
            return entry[1]
        try:
            profile = read_employee_profile(self.url, self.secret, employee_id)
            lifetime = PROFILE_TTL_SECONDS
        except McpProfileError as exc:
            logger.warning("%s", exc)
            profile, lifetime = None, PROFILE_RETRY_SECONDS
        self._entries[employee_id] = (self._clock() + lifetime, profile)
        return profile
