"""Typed contracts shared by the agent, its UI, and the MCP tools it calls."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class HelpdeskContext:
    """Trusted per-run context supplied by the application, never by the model."""

    employee_id: str


LeaveType = Literal["annual", "sick", "carry_forward"]
TicketCategory = Literal[
    "VPN", "Network", "Hardware", "Software", "MFA", "Email", "Access", "Printer", "Other"
]
TicketPriority = Literal["low", "medium", "high", "urgent"]


class ToolObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    outcome: Literal["success", "not_found", "not_authorized", "error"]
    detail: str
