"""Typed, read-only tools bound to trusted application-provided identity."""

from __future__ import annotations

from typing import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, tool
from pydantic import Field

from data.repository import HelpdeskRepository
from domain import HelpdeskContext, LeaveType, TicketCategory, TicketPriority


def create_helpdesk_tools(repository: HelpdeskRepository) -> list[BaseTool]:
    """Create tools that read the employee ID from runtime context, not model arguments."""

    @tool
    def get_ticket_status(
        ticket_id: str, runtime: ToolRuntime[HelpdeskContext]
    ) -> dict[str, object]:
        """Get status, priority, assignee, title, and last-updated time for a ticket you own. Use the exact ticket ID such as INC-1042. Access to another employee's ticket is restricted."""
        return repository.get_ticket_status(
            ticket_id, runtime.context.employee_id
        ).model_dump()

    @tool
    def list_my_tickets(runtime: ToolRuntime[HelpdeskContext]) -> dict[str, object]:
        """List the signed-in employee's helpdesk tickets, including status and priority. This tool only returns tickets belonging to the current employee."""
        return repository.list_my_tickets(runtime.context.employee_id).model_dump()

    @tool
    def check_leave_balance(runtime: ToolRuntime[HelpdeskContext]) -> dict[str, object]:
        """Check annual, sick, carry-forward, and total remaining leave for the signed-in employee. Never accept an employee ID from the user."""
        return repository.check_leave_balance(runtime.context.employee_id).model_dump()

    @tool
    def create_ticket(
        title: Annotated[str, Field(min_length=5, max_length=120)],
        description: Annotated[str, Field(min_length=10, max_length=2000)],
        category: TicketCategory,
        priority: TicketPriority,
        runtime: ToolRuntime[HelpdeskContext],
    ) -> dict[str, object]:
        """Create a new helpdesk ticket for the signed-in employee. Write action: the user must approve the draft before it runs. Provide a concise title, a description of the problem, a category and a priority (default medium unless the user states urgency)."""
        # tool_call_id is stable across the approval resume, so a repeat cannot double-create.
        return repository.create_ticket(
            runtime.context.employee_id,
            title.strip(),
            description.strip(),
            category,
            priority,
            idempotency_key=f"create_ticket:{runtime.tool_call_id}",
        ).model_dump()

    @tool
    def get_leave_history(runtime: ToolRuntime[HelpdeskContext]) -> dict[str, object]:
        """List the signed-in employee's past and pending leave requests with type, dates, days and status. Only returns the current employee's own history."""
        return repository.get_leave_history(runtime.context.employee_id).model_dump()

    @tool
    def apply_leave(
        leave_type: LeaveType,
        start_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        end_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        reason: Annotated[str, Field(max_length=500)],
        runtime: ToolRuntime[HelpdeskContext],
    ) -> dict[str, object]:
        """Submit a leave request for the signed-in employee. Write action: the user must approve the draft before it runs. Dates are ISO YYYY-MM-DD (inclusive); resolve relative dates like 'next Friday' to exact dates first. Weekends are not counted. Check the balance with check_leave_balance first when unsure."""
        return repository.apply_leave(
            runtime.context.employee_id,
            leave_type,
            start_date,
            end_date,
            reason.strip(),
            idempotency_key=f"apply_leave:{runtime.tool_call_id}",
        ).model_dump()

    return [
        get_ticket_status,
        list_my_tickets,
        check_leave_balance,
        create_ticket,
        get_leave_history,
        apply_leave,
    ]
