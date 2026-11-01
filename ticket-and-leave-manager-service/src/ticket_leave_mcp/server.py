"""FastMCP server exposing ticket and leave tools, a profile resource and sample prompts over streamable HTTP."""

from __future__ import annotations

from datetime import date
from typing import Annotated, get_args

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth import (
    AuthError,
    employee_id_from_headers,
    idempotency_key_from_headers,
)
from .config import Settings
from .domain import LeaveType, TicketCategory, TicketPriority
from .repository import HelpdeskRepository

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
CATEGORIES = ", ".join(get_args(TicketCategory))
PRIORITIES = ", ".join(get_args(TicketPriority))
LEAVE_TYPES = ", ".join(get_args(LeaveType))


def register_prompts(mcp: FastMCP) -> None:
    """Offer sample prompt templates a user can pick; they only return text and call nothing."""

    @mcp.prompt(title="Raise an IT ticket")
    def raise_it_ticket(
        issue: Annotated[
            str, Field(description="What is wrong, in the employee's words.", max_length=2000)
        ],
        category: Annotated[
            TicketCategory | None, Field(description=f"Ticket category, if known: {CATEGORIES}.")
        ] = None,
    ) -> str:
        """Draft a helpdesk ticket for a problem, then submit it with create_ticket."""
        return "\n".join(
            [
                f"Employee problem: {issue}",
                f"Category: {category or 'not given'}",
                "",
                "Raise a helpdesk ticket for this problem:",
                "1. Draft the ticket: a concise title, a description of the problem (facts only; "
                "never passwords, tokens or one-time codes), a category (the one above if given, "
                f"otherwise one of {CATEGORIES}) and a priority ({PRIORITIES}; medium unless the "
                "employee states urgency). Ask for anything required that you cannot infer.",
                "2. Call create_ticket once with the draft. Do not say the ticket exists until "
                "the tool result confirms it.",
            ]
        )

    @mcp.prompt(title="Request leave")
    def request_leave(
        leave_type: Annotated[LeaveType, Field(description=f"One of: {LEAVE_TYPES}.")],
        when: Annotated[
            str,
            Field(description="The dates in their own words, e.g. 'next Friday'.", max_length=100),
        ],
        reason: Annotated[
            str, Field(description="Optional reason for the leave.", max_length=500)
        ] = "",
    ) -> str:
        """Plan a leave request: work out the dates, check the balance, then submit it with apply_leave."""
        return "\n".join(
            [
                f"The employee wants {leave_type} leave: {when}",
                f"Reason: {reason.strip() or 'none given'}",
                f"Today's date: {date.today().isoformat()}",
                "",
                "Request this leave:",
                "1. Work out the exact start and end dates (YYYY-MM-DD, inclusive). Ask if they "
                "are unclear.",
                "2. Call check_leave_balance. Weekends are not counted; if too few days remain, "
                "say so instead of submitting.",
                "3. Call apply_leave once with the exact dates and the reason. Do not say the "
                "request was submitted until the tool result confirms it.",
            ]
        )

    @mcp.prompt(title="Summarize my tickets")
    def summarize_my_tickets() -> str:
        """Summarize the signed-in employee's helpdesk tickets using list_my_tickets."""
        return (
            "Call list_my_tickets, then summarize the employee's tickets: group them by status, "
            "call out anything high or urgent, and name the most recently updated ticket. "
            "Use only what the tool returns. If there are no tickets, say so."
        )

    @mcp.prompt(title="Leave overview")
    def leave_overview() -> str:
        """Summarize the signed-in employee's leave balance and requests."""
        return (
            "Call check_leave_balance and get_leave_history, then give a short overview: the "
            "remaining annual, sick and carry-forward days with the total, and any pending "
            "requests with their dates. Use only what the tools return."
        )


def create_server(settings: Settings, repository: HelpdeskRepository | None = None) -> FastMCP:
    repository = repository or HelpdeskRepository(settings.database_path)
    mcp = FastMCP(
        "ticket-and-leave-manager",
        host=settings.host,
        port=settings.port,
        stateless_http=True,
        json_response=True,
    )

    def headers(ctx: Context) -> dict[str, str]:
        request = ctx.request_context.request
        if request is None:
            raise ValueError("This server only accepts HTTP requests.")
        return dict(request.headers)

    def employee(ctx: Context) -> str:
        return employee_id_from_headers(headers(ctx), settings.jwt_secret)

    @mcp.tool(annotations=READ_ONLY)
    def get_ticket_status(ticket_id: str, ctx: Context) -> dict[str, object]:
        """Get status, priority, assignee, title, and last-updated time for a ticket you own. Use the exact ticket ID such as INC-1042. Access to another employee's ticket is restricted."""
        return repository.get_ticket_status(ticket_id, employee(ctx)).model_dump()

    @mcp.tool(annotations=READ_ONLY)
    def list_my_tickets(ctx: Context) -> dict[str, object]:
        """List the signed-in employee's helpdesk tickets, including status and priority. This tool only returns tickets belonging to the current employee."""
        return repository.list_my_tickets(employee(ctx)).model_dump()

    @mcp.tool(annotations=READ_ONLY)
    def check_leave_balance(ctx: Context) -> dict[str, object]:
        """Check annual, sick, carry-forward, and total remaining leave for the signed-in employee. Never accept an employee ID from the user."""
        return repository.check_leave_balance(employee(ctx)).model_dump()

    @mcp.tool(annotations=READ_ONLY)
    def get_leave_history(ctx: Context) -> dict[str, object]:
        """List the signed-in employee's past and pending leave requests with type, dates, days and status. Only returns the current employee's own history."""
        return repository.get_leave_history(employee(ctx)).model_dump()

    @mcp.tool(annotations=WRITE)
    def create_ticket(
        title: Annotated[str, Field(min_length=5, max_length=120)],
        description: Annotated[str, Field(min_length=10, max_length=2000)],
        category: TicketCategory,
        priority: TicketPriority,
        ctx: Context,
    ) -> dict[str, object]:
        """Create a new helpdesk ticket for the signed-in employee. Write action: the user must approve the draft before it runs. Provide a concise title, a description of the problem, a category and a priority (default medium unless the user states urgency)."""
        request_headers = headers(ctx)
        return repository.create_ticket(
            employee_id_from_headers(request_headers, settings.jwt_secret),
            title.strip(),
            description.strip(),
            category,
            priority,
            idempotency_key=idempotency_key_from_headers(request_headers),
        ).model_dump()

    @mcp.tool(annotations=WRITE)
    def apply_leave(
        leave_type: LeaveType,
        start_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        end_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        reason: Annotated[str, Field(max_length=500)],
        ctx: Context,
    ) -> dict[str, object]:
        """Submit a leave request for the signed-in employee. Write action: the user must approve the draft before it runs. Dates are ISO YYYY-MM-DD (inclusive); resolve relative dates like 'next Friday' to exact dates first. Weekends are not counted. Check the balance with check_leave_balance first when unsure."""
        request_headers = headers(ctx)
        return repository.apply_leave(
            employee_id_from_headers(request_headers, settings.jwt_secret),
            leave_type,
            start_date,
            end_date,
            reason.strip(),
            idempotency_key=idempotency_key_from_headers(request_headers),
        ).model_dump()

    # No parameters on purpose: FastMCP registers a resource function that takes any (even a
    # Context) as a template, which hides it from resources/list. The employee comes from the
    # token, so neither the URI nor the function accepts an employee ID.
    @mcp.resource("employee://me/profile", title="My employee profile", mime_type="application/json")
    def my_profile() -> str:
        """The signed-in employee's name, department, office and manager. Taken from the bearer token; no employee ID is accepted."""
        profile = repository.get_my_profile(employee(mcp.get_context()))
        if profile is None:
            raise ValueError("No active employee for this token.")
        return profile.model_dump_json()

    register_prompts(mcp)
    return mcp


class JwtAuthMiddleware:
    """Rejects every HTTP request without a valid bearer token before MCP handles it."""

    def __init__(self, app: ASGIApp, secret: str) -> None:
        self.app = app
        self.secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            request_headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            try:
                employee_id_from_headers(request_headers, self.secret)
            except AuthError as exc:
                response = JSONResponse(
                    {"error": str(exc)}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(settings: Settings, repository: HelpdeskRepository | None = None) -> ASGIApp:
    """ASGI app serving MCP at /mcp, with JWT required on every request."""
    app = create_server(settings, repository).streamable_http_app()
    return JwtAuthMiddleware(app, settings.jwt_secret)
