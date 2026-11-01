"""SQLite repository; reads are query-only and the single write path is explicit."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .domain import (
    EmployeeProfile,
    LeaveApplyResult,
    LeaveBalanceResult,
    LeaveHistoryResult,
    LeaveRequestSummary,
    TicketCreateResult,
    TicketListResult,
    TicketResult,
    TicketSummary,
)


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

    def create_ticket(
        self,
        employee_id: str,
        title: str,
        description: str,
        category: str,
        priority: str,
        idempotency_key: str,
    ) -> TicketCreateResult:
        """Create a ticket once per idempotency key; a repeat returns the original ticket."""
        with self._write() as connection:
            existing = self._existing_payload(connection, idempotency_key)
            if existing:
                ticket_id = existing["ticket_id"]
                return TicketCreateResult(
                    created=False,
                    ticket_id=ticket_id,
                    status="open",
                    message=f"Ticket {ticket_id} was already created for this approval.",
                )
            if self._manager_of(connection, employee_id) is None:
                return TicketCreateResult(created=False, message="Employee is not active.")
            ticket_id = f"INC-{self._next_number(connection, 'tickets', 'ticket_id'):04d}"
            now = _now()
            connection.execute(
                """INSERT INTO tickets (ticket_id, owner_employee_id, title, description,
                       category, status, priority, assigned_to, created_at, updated_at, notes)
                   VALUES (?, ?, ?, ?, ?, 'open', ?, 'Unassigned', ?, ?, '')""",
                (ticket_id, employee_id, title, description, category, priority, now, now),
            )
            self._record_approval(
                connection, "create_ticket", employee_id, employee_id, idempotency_key,
                {
                    "ticket_id": ticket_id,
                    "title": title,
                    "description": description,
                    "category": category,
                    "priority": priority,
                },
            )
        return TicketCreateResult(
            created=True, ticket_id=ticket_id, status="open", message=f"Created ticket {ticket_id}."
        )

    def get_leave_history(self, employee_id: str) -> LeaveHistoryResult:
        """Return only the current employee's leave requests, newest first."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT request_id, leave_type, start_date, end_date, days, status, notes
                   FROM leave_history WHERE employee_id = ?
                   ORDER BY start_date DESC, request_id DESC""",
                (employee_id,),
            ).fetchall()
        requests = [LeaveRequestSummary(**dict(row)) for row in rows]
        return LeaveHistoryResult(
            requests=requests, message=f"Found {len(requests)} leave request(s)."
        )

    def get_my_profile(self, employee_id: str) -> EmployeeProfile | None:
        """Return the employee's profile, or None when they are not an active employee."""
        with self._connect() as connection:
            row = connection.execute(
                """SELECT e.employee_id, e.full_name, e.department, e.office_location,
                          m.full_name AS manager_name
                   FROM employees AS e LEFT JOIN employees AS m ON m.employee_id = e.manager_id
                   WHERE e.employee_id = ? AND e.active = 1""",
                (employee_id,),
            ).fetchone()
        return EmployeeProfile(**dict(row)) if row else None

    def apply_leave(
        self,
        employee_id: str,
        leave_type: str,
        start_date: str,
        end_date: str,
        reason: str,
        idempotency_key: str,
    ) -> LeaveApplyResult:
        """Submit a pending leave request for weekdays in the range, after validating balance."""
        try:
            start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        except ValueError:
            return LeaveApplyResult(created=False, message="Dates must be valid YYYY-MM-DD values.")
        if end < start:
            return LeaveApplyResult(created=False, message="The end date is before the start date.")
        if start < date.today() and leave_type != "sick":
            return LeaveApplyResult(created=False, message="Leave cannot start in the past.")
        days = float(sum(1 for i in range((end - start).days + 1) if (start + timedelta(i)).weekday() < 5))
        if days == 0:
            return LeaveApplyResult(created=False, message="The range contains no working days.")

        with self._write() as connection:
            existing = self._existing_payload(connection, idempotency_key)
            if existing:
                return LeaveApplyResult(
                    created=False,
                    request_id=existing["request_id"],
                    days=existing["days"],
                    status="pending",
                    message=f"Leave request {existing['request_id']} was already submitted.",
                )
            manager = self._manager_of(connection, employee_id)
            if manager is None:
                return LeaveApplyResult(created=False, message="Employee is not active.")
            balance = connection.execute(
                f"""SELECT {leave_type}_entitlement - {leave_type}_used AS remaining
                    FROM leave_balances WHERE employee_id = ?""",  # leave_type is a validated Literal
                (employee_id,),
            ).fetchone()
            if balance is None:
                return LeaveApplyResult(created=False, message="No leave balance was found.")
            pending_days = connection.execute(
                """SELECT COALESCE(SUM(days), 0) FROM leave_history
                   WHERE employee_id = ? AND leave_type = ? AND status = 'pending'""",
                (employee_id, leave_type),
            ).fetchone()[0]
            remaining = balance["remaining"] - pending_days
            if days > remaining:
                return LeaveApplyResult(
                    created=False,
                    days=days,
                    message=f"Insufficient {leave_type} leave: {days:g} day(s) requested, "
                    f"{remaining:g} available.",
                )
            overlap = connection.execute(
                """SELECT request_id FROM leave_history
                   WHERE employee_id = ? AND status IN ('approved', 'pending')
                     AND start_date <= ? AND end_date >= ?""",
                (employee_id, end_date, start_date),
            ).fetchone()
            if overlap:
                return LeaveApplyResult(
                    created=False, message=f"These dates overlap leave request {overlap['request_id']}."
                )
            request_id = f"LR-{self._next_number(connection, 'leave_history', 'request_id'):04d}"
            connection.execute(
                """INSERT INTO leave_history (request_id, employee_id, leave_type, start_date,
                       end_date, days, status, submitted_at, approver_employee_id, notes)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                (request_id, employee_id, leave_type, start_date, end_date, days, _now(), manager, reason),
            )
            self._record_approval(
                connection, "apply_leave", employee_id, manager, idempotency_key,
                {"request_id": request_id, "leave_type": leave_type, "start_date": start_date,
                 "end_date": end_date, "days": days, "reason": reason},
            )
        return LeaveApplyResult(
            created=True,
            request_id=request_id,
            days=days,
            status="pending",
            message=f"Submitted leave request {request_id} for {days:g} working day(s); "
            "it awaits manager approval.",
        )

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """One immediate transaction: commits on success, rolls back on any error."""
        if not self.database_path.is_file():
            raise FileNotFoundError(f"Helpdesk database not found at {self.database_path}.")
        with closing(sqlite3.connect(self.database_path, isolation_level=None)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _existing_payload(connection: sqlite3.Connection, key: str) -> dict | None:
        row = connection.execute(
            "SELECT payload_json FROM approval_requests WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    @staticmethod
    def _manager_of(connection: sqlite3.Connection, employee_id: str) -> str | None:
        """Return the approver for an active employee (self if they have no manager)."""
        row = connection.execute(
            "SELECT manager_id FROM employees WHERE employee_id = ? AND active = 1", (employee_id,)
        ).fetchone()
        if row is None:
            return None
        return row["manager_id"] or employee_id

    @staticmethod
    def _next_number(connection: sqlite3.Connection, table: str, column: str) -> int:
        # table/column are internal constants, never user input.
        return connection.execute(
            f"SELECT COALESCE(MAX(CAST(SUBSTR({column}, INSTR({column}, '-') + 1) AS INTEGER)), 0) + 1 "
            f"FROM {table}"
        ).fetchone()[0]

    def _record_approval(
        self,
        connection: sqlite3.Connection,
        action_type: str,
        requester: str,
        approver: str,
        idempotency_key: str,
        payload: dict,
    ) -> None:
        now = _now()
        number = self._next_number(connection, "approval_requests", "approval_id")
        connection.execute(
            """INSERT INTO approval_requests (approval_id, action_type, requester_employee_id,
                   approver_employee_id, status, payload_json, idempotency_key, created_at,
                   resolved_at)
               VALUES (?, ?, ?, ?, 'approved', ?, ?, ?, ?)""",
            (f"APR-{number:04d}", action_type, requester, approver, json.dumps(payload),
             idempotency_key, now, now),
        )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
