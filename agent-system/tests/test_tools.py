from pathlib import Path

from build_database import build_database
from data.repository import HelpdeskRepository
from tools.helpdesk import create_helpdesk_tools


def test_tools_do_not_accept_model_selected_employee_identity(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    tools = {item.name: item for item in create_helpdesk_tools(HelpdeskRepository(database), "E104")}

    assert set(tools) == {"get_ticket_status", "list_my_tickets", "check_leave_balance"}
    assert "employee_id" not in tools["check_leave_balance"].args
    assert "employee_id" not in tools["list_my_tickets"].args


def test_ticket_tool_uses_identity_bound_by_application(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    tools = {item.name: item for item in create_helpdesk_tools(HelpdeskRepository(database), "E104")}

    result = tools["get_ticket_status"].invoke({"ticket_id": "INC-1042"})

    assert result["found"] is True
    assert result["priority"] == "high"
