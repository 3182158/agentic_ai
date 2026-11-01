from cli import (
    _content_as_text,
    _create_input_bindings,
    parse_command,
    parse_prompt_command,
    run_chat,
)
from config import Settings
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.keys import Keys

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console

from agents.agent import build_agent
from memory.store import ConversationStore


def test_parse_command_is_case_insensitive_and_accepts_arguments() -> None:
    assert parse_command("  /HeLp  ") == ("help", "")
    assert parse_command("/model test-model") == ("model", "test-model")


def test_parse_command_ignores_regular_chat_messages() -> None:
    assert parse_command("What is my leave balance?") is None


def test_content_as_text_handles_langchain_text_blocks() -> None:
    content = [
        {"type": "text", "text": "First paragraph."},
        {"type": "image", "url": "ignored"},
        {"type": "text", "text": "Second paragraph."},
    ]

    assert _content_as_text(content) == "First paragraph.\nSecond paragraph."


def test_enter_and_shift_enter_are_distinct_input_keys() -> None:
    assert ANSI_SEQUENCES["\x1b[27;2;13~"] == Keys.ControlJ
    assert ANSI_SEQUENCES["\x1b[13;2u"] == Keys.ControlJ
    assert ANSI_SEQUENCES["\x0a"] == Keys.ControlM
    bindings = _create_input_bindings()
    assert bindings.get_bindings_for_keys((Keys.ControlM,))
    assert bindings.get_bindings_for_keys((Keys.ControlJ,))


def _settings(tmp_path, **overrides) -> Settings:
    return Settings(
        "E104", "test-model", 4, tmp_path / "memory.sqlite3",
        **{"mcp_url": "http://127.0.0.1:9/mcp", "mcp_secret": "x" * 32, **overrides},
    )


def test_run_chat_reports_an_unreachable_mcp_server(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr("cli.get_settings", lambda: _settings(tmp_path))

    run_chat()

    output = capsys.readouterr().out
    assert "Cannot load tools from the helpdesk MCP server" in output
    assert "HELPDESK_MCP_SECRET" in output


def test_run_chat_reports_a_missing_mcp_secret(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr("cli.get_settings", lambda: _settings(tmp_path, mcp_secret=""))

    run_chat()

    assert "HELPDESK_MCP_SECRET is not set" in capsys.readouterr().out


def test_parse_prompt_command_reads_a_name_and_quoted_values() -> None:
    assert parse_prompt_command(
        'raise_it_ticket issue="VPN drops every ten minutes" category=VPN'
    ) == ("raise_it_ticket", {"issue": "VPN drops every ten minutes", "category": "VPN"})
    assert parse_prompt_command("leave_overview") == ("leave_overview", {})
    assert parse_prompt_command("request_leave reason=a=b") == ("request_leave", {"reason": "a=b"})


@pytest.mark.parametrize(
    "argument, message",
    [
        ("", "Usage"),
        ("issue=VPN", "Usage"),
        ("raise_it_ticket issue", "key=value"),
        ('raise_it_ticket issue="unclosed', "Could not read"),
    ],
)
def test_parse_prompt_command_explains_bad_input(argument, message) -> None:
    with pytest.raises(ValueError, match=message):
        parse_prompt_command(argument)


class _Typing:
    """Stands in for the interactive prompt: types the given lines, then ends the chat."""

    def __init__(self, *lines: str) -> None:
        self.lines = list(lines)

    def __call__(self, *args, **kwargs):
        return self

    def prompt(self, message: str) -> str:
        if not self.lines:
            raise EOFError
        return self.lines.pop(0)


class _TicketListModel:
    """Asks for list_my_tickets, then answers; remembers what it was shown."""

    def __init__(self) -> None:
        self.seen: list[list] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.seen.append(messages)
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="You have three tickets.")
        call = {"name": "list_my_tickets", "args": {}, "id": "t1", "type": "tool_call"}
        return AIMessage(content="", tool_calls=[call])


def _chat(monkeypatch, capsys, mcp_service, *lines: str, employee_id: str | None = None):
    """Run the real chat loop against the real MCP service with typed lines and a fake model."""
    model = _TicketListModel()
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr("cli.get_settings", lambda: mcp_service.settings)
    monkeypatch.setattr("cli.PromptSession", _Typing(*lines))
    monkeypatch.setattr("cli.console", Console(width=200))
    monkeypatch.setattr(
        "cli.build_agent", lambda settings, **kwargs: build_agent(settings, model=model, **kwargs)
    )
    run_chat(employee_id)
    return model, capsys.readouterr().out


def test_help_lists_the_prompt_commands(monkeypatch, capsys, mcp_service) -> None:
    _, output = _chat(monkeypatch, capsys, mcp_service, "/help")

    assert "/prompts" in output
    assert "/prompt <name> key=value" in output


def test_banner_and_whoami_show_the_employee_profile(monkeypatch, capsys, mcp_service) -> None:
    held = mcp_service.repository.get_my_profile("E104")
    summary = f"{held.full_name} · {held.department} · {held.office_location}"

    _, output = _chat(monkeypatch, capsys, mcp_service, "/whoami")

    assert f"Signed in as demo employee E104 ({summary})" in output
    assert output.count(summary) == 2  # the banner, then /whoami
    assert f"Manager: {held.manager_name}" in output


def test_chat_works_for_an_employee_without_a_profile(monkeypatch, capsys, mcp_service) -> None:
    _, output = _chat(monkeypatch, capsys, mcp_service, "/whoami", employee_id="E999")

    assert "Signed in as demo employee E999." in output
    assert "Configured demo identity: E999" in output
    assert "Manager:" not in output


def test_prompts_command_lists_the_servers_templates(monkeypatch, capsys, mcp_service) -> None:
    model, output = _chat(monkeypatch, capsys, mcp_service, "/prompts")

    for name in ("raise_it_ticket", "request_leave", "summarize_my_tickets", "leave_overview"):
        assert name in output
    assert "category (optional)" in output
    assert model.seen == []


def test_prompt_command_sends_the_rendered_text_and_keeps_a_short_transcript(
    monkeypatch, capsys, mcp_service
) -> None:
    model, output = _chat(monkeypatch, capsys, mcp_service, "/prompt summarize_my_tickets")

    sent = [m.content for m in model.seen[0] if isinstance(m, HumanMessage)]
    assert len(sent) == 1 and "list_my_tickets" in sent[0]
    assert "You have three tickets." in output
    store = ConversationStore(mcp_service.settings.memory_database_path)
    (conversation,) = store.list_conversations("E104")
    transcript = store.get_messages(conversation["thread_id"], "E104")
    assert [m["content"] for m in transcript] == ["Summarize my tickets", "You have three tickets."]


def test_prompt_command_passes_quoted_arguments_to_the_template(
    monkeypatch, capsys, mcp_service
) -> None:
    model, _ = _chat(
        monkeypatch,
        capsys,
        mcp_service,
        '/prompt raise_it_ticket issue="VPN drops every ten minutes" category=VPN',
    )

    sent = [m.content for m in model.seen[0] if isinstance(m, HumanMessage)]
    assert "Employee problem: VPN drops every ten minutes" in sent[0]
    assert "Category: VPN" in sent[0]


@pytest.mark.parametrize(
    "line, explained",
    [
        ("/prompt", "Usage"),
        ("/prompt nope", "Unknown prompt 'nope'"),
        ("/prompt raise_it_ticket", "needs issue"),
        ("/prompt leave_overview foo=bar", "has no argument foo"),
        ("/prompt request_leave leave_type=bogus when=tomorrow", "leave_type"),
    ],
)
def test_bad_prompt_command_is_explained_and_nothing_is_sent(
    monkeypatch, capsys, mcp_service, line, explained
) -> None:
    model, output = _chat(monkeypatch, capsys, mcp_service, line)

    assert explained in output
    assert model.seen == []