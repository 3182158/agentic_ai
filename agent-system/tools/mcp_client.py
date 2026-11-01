"""Helpdesk tools loaded straight from the ticket-and-leave MCP server."""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

import jwt
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, ToolCallInterceptor
from mcp.types import CallToolResult, TextContent

from domain import HelpdeskContext

TOKEN_TTL_SECONDS = 60
SERVICE_SUBJECT = "helpdesk-agent"


class McpSetupError(RuntimeError):
    """The helpdesk MCP server is not configured or cannot be reached."""


def _token(subject: str, secret: str) -> str:
    claims = {"sub": subject, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(claims, secret, algorithm="HS256")


def _reason(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup):  # anyio wraps transport errors in a task group
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}".splitlines()[0]


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
