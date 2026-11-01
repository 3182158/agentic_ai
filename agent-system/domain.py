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


class EmployeeProfile(BaseModel):
    """The signed-in employee's directory profile, read from the MCP service as a resource.

    Extra fields are ignored, so the server's employee ID never reaches the model.
    """

    model_config = ConfigDict(extra="ignore")

    full_name: str
    department: str
    office_location: str
    manager_name: str | None = None

    def summary(self) -> str:
        return " · ".join((self.full_name, self.department, self.office_location))
