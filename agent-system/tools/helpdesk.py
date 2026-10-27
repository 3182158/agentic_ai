"""Typed, read-only tools bound to trusted application-provided identity."""

from __future__ import annotations

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, tool

from data.repository import HelpdeskRepository
from domain import HelpdeskContext


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

    return [get_ticket_status, list_my_tickets, check_leave_balance]
