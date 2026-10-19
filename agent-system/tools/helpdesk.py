"""Typed, read-only tools bound to trusted application-provided identity."""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from data.repository import HelpdeskRepository


def create_helpdesk_tools(
    repository: HelpdeskRepository, employee_id: str
) -> list[BaseTool]:
    """Create tools whose data scope is fixed outside model-controlled arguments."""

    @tool
    def get_ticket_status(ticket_id: str) -> dict[str, object]:
        """Get status, priority, assignee, title, and last-updated time for a ticket you own. Use the exact ticket ID such as INC-1042. Access to another employee's ticket is restricted."""
        return repository.get_ticket_status(ticket_id, employee_id).model_dump()

    @tool
    def list_my_tickets() -> dict[str, object]:
        """List the signed-in employee's helpdesk tickets, including status and priority. This tool only returns tickets belonging to the current employee."""
        return repository.list_my_tickets(employee_id).model_dump()

    @tool
    def check_leave_balance() -> dict[str, object]:
        """Check annual, sick, carry-forward, and total remaining leave for the signed-in employee. Never accept an employee ID from the user."""
        return repository.check_leave_balance(employee_id).model_dump()

    return [get_ticket_status, list_my_tickets, check_leave_balance]
