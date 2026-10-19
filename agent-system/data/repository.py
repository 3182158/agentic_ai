"""Small read-only SQLite repository; replaceable independently of the agent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from domain import LeaveBalanceResult, TicketListResult, TicketResult, TicketSummary


class HelpdeskRepository:
    """Read helpdesk records without exposing SQL or connections to the model."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise FileNotFoundError(
                f"Helpdesk database not found at {self.database_path}. "
                "Build it with: uv run python mock-data/sqlite/build_database.py"
            )
        connection = sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def get_ticket_status(self, ticket_id: str, employee_id: str) -> TicketResult:
        """Look up a ticket, allowing its owner or an IT admin to see details."""
        normalized_id = ticket_id.strip().upper()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT t.ticket_id, t.owner_employee_id, t.title, t.status,
                          t.priority, t.assigned_to, t.updated_at, e.access_role
                   FROM tickets AS t JOIN employees AS e ON e.employee_id = ?
                   WHERE t.ticket_id = ?""",
                (employee_id, normalized_id),
            ).fetchone()

        if row is None:
            return TicketResult(found=False, ticket_id=normalized_id, message="Ticket not found.")
        if row["owner_employee_id"] != employee_id and row["access_role"] != "it_admin":
            return TicketResult(
                found=False,
                ticket_id=normalized_id,
                message="You are not authorized to view this ticket.",
            )
        return TicketResult(
            found=True,
            ticket_id=row["ticket_id"],
            title=row["title"],
            status=row["status"],
            priority=row["priority"],
            assigned_to=row["assigned_to"],
            updated_at=row["updated_at"],
        )

    def list_my_tickets(self, employee_id: str) -> TicketListResult:
        """List only the current employee's tickets, newest updates first."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT ticket_id, title, status, priority, updated_at
                   FROM tickets WHERE owner_employee_id = ?
                   ORDER BY updated_at DESC, ticket_id""",
                (employee_id,),
            ).fetchall()
        tickets = [TicketSummary(**dict(row)) for row in rows]
        return TicketListResult(
            tickets=tickets,
            message=f"Found {len(tickets)} ticket(s) for the signed-in demo employee.",
        )

    def check_leave_balance(self, employee_id: str) -> LeaveBalanceResult:
        """Return the current employee's leave balances from the summary view."""
        with self._connect() as connection:
            row = connection.execute(
                """SELECT employee_id, annual_remaining, sick_remaining,
                          carry_forward_remaining, total_remaining, as_of_date
                   FROM leave_balance_summary WHERE employee_id = ?""",
                (employee_id,),
            ).fetchone()
        if row is None:
            return LeaveBalanceResult(
                found=False, employee_id=employee_id, message="No leave balance was found."
            )
        return LeaveBalanceResult(found=True, **dict(row))
