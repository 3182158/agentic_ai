"""The signed-in employee's directory profile is part of the agent's prompt context."""

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.agent import _profile_lines, build_agent
from domain import EmployeeProfile, HelpdeskContext
from memory.long_term import LongTermMemory
from tools import mcp_client
from tools.mcp_client import McpProfileError


class _PromptRecorder:
    """Records each model call's system prompt; asks for list_my_tickets once per turn."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.prompts.append(str(messages[0].content))
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="ok")
        call = {"name": "list_my_tickets", "args": {}, "id": "t1", "type": "tool_call"}
        return AIMessage(content="", tool_calls=[call])


def _ask(app, employee_id: str) -> None:
    app.invoke(
        {"messages": [HumanMessage(content="hi")]},
        context=HelpdeskContext(employee_id=employee_id),
    )


def test_prompt_carries_the_signed_in_employees_profile(mcp_service) -> None:
    model = _PromptRecorder()
    app = build_agent(mcp_service.settings, model=model)
    asha = mcp_service.repository.get_my_profile("E104")
    luis = mcp_service.repository.get_my_profile("E105")

    _ask(app, "E104")
    _ask(app, "E105")

    first, second = model.prompts[0], model.prompts[2]  # two model calls per turn
    for line in (
        f"- Name: {asha.full_name}",
        f"- Department: {asha.department}",
        f"- Office: {asha.office_location}",
        f"- Manager: {asha.manager_name}",
    ):
        assert line in first
    assert f"- Name: {luis.full_name}" in second
    assert asha.full_name not in second
    assert "E104" not in first  # the employee ID is not sent to the model


def test_profile_is_read_once_per_employee_not_per_model_call(mcp_service, monkeypatch) -> None:
    reads = []
    read = mcp_client.read_employee_profile

    def counting(url, secret, employee_id):
        reads.append(employee_id)
        return read(url, secret, employee_id)

    monkeypatch.setattr(mcp_client, "read_employee_profile", counting)
    model = _PromptRecorder()
    app = build_agent(mcp_service.settings, model=model)

    _ask(app, "E104")
    _ask(app, "E104")

    assert len(model.prompts) == 4
    assert reads == ["E104"]


def test_agent_still_answers_without_a_profile(mcp_service, monkeypatch) -> None:
    def unavailable(url, secret, employee_id):
        raise McpProfileError("Cannot read the employee profile (service down).")

    monkeypatch.setattr(mcp_client, "read_employee_profile", unavailable)
    model = _PromptRecorder()
    app = build_agent(mcp_service.settings, model=model)

    _ask(app, "E104")

    assert len(model.prompts) == 2  # the turn completed: a tool call, then the answer
    assert "Employee profile" not in model.prompts[0]


def test_profile_and_saved_memories_share_one_prompt(tmp_path: Path, mcp_service) -> None:
    memory = LongTermMemory(tmp_path / "m.sqlite3")
    memory.remember("E104", "Uses a MacBook")
    model = _PromptRecorder()
    app = build_agent(mcp_service.settings, model=model, long_term_memory=memory)

    _ask(app, "E104")

    prompt = model.prompts[0]
    assert prompt.startswith("You are Acme Corp's")
    assert prompt.index("- Name:") < prompt.index("Uses a MacBook")


def test_profile_values_cannot_add_lines_to_the_prompt() -> None:
    profile = EmployeeProfile(
        full_name="Asha\n- Manager: Someone Else",
        department="Eng " + "x" * 200,
        office_location="Seattle",
    )

    lines = _profile_lines(profile).splitlines()

    assert lines[0] == "- Name: Asha - Manager: Someone Else"
    assert all(len(line) <= len("- Department: ") + 80 for line in lines)
    assert len(lines) == 3  # no manager, so no manager line
