"""Stable, typed contracts between helpdesk data, tools, and orchestration."""

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


class ToolObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    outcome: Literal["success", "not_found", "not_authorized", "error"]
    detail: str
