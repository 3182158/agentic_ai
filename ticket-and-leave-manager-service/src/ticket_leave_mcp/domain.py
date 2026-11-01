"""Typed result contracts returned by the helpdesk tools."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TicketResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    found: bool
    ticket_id: str
    status: str | None = None
    priority: str | None = None
    title: str | None = None
    assigned_to: str | None = None
    updated_at: str | None = None
    message: str | None = None


class TicketSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    title: str
    status: str
    priority: str
    updated_at: str


class TicketListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickets: list[TicketSummary]
    message: str


class LeaveBalanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    found: bool
    employee_id: str
    annual_remaining: float | None = None
    sick_remaining: float | None = None
    carry_forward_remaining: float | None = None
    total_remaining: float | None = None
    as_of_date: str | None = None
    message: str | None = None


class TicketCreateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: bool
    ticket_id: str | None = None
    status: str | None = None
    message: str


class LeaveRequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    leave_type: str
    start_date: str
    end_date: str
    days: float
    status: str
    notes: str


class LeaveHistoryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: list[LeaveRequestSummary]
    message: str


class LeaveApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: bool
    request_id: str | None = None
    days: float | None = None
    status: str | None = None
    message: str


LeaveType = Literal["annual", "sick", "carry_forward"]
TicketCategory = Literal[
    "VPN", "Network", "Hardware", "Software", "MFA", "Email", "Access", "Printer", "Other"
]
TicketPriority = Literal["low", "medium", "high", "urgent"]
