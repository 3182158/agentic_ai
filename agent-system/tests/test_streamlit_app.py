"""UI regressions without provider calls or external tracing."""

import logging
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from openai import AuthenticationError
from streamlit.testing.v1 import AppTest

from streamlit_app import _content_as_text, _tracing_enabled
from memory.service import ChatService
from memory.store import ConversationStore
from tools.mcp_client import McpSetupError, list_helpdesk_prompts


def _no_profiles(url, secret):
    """Stands in for the profile reader in tests that run without an MCP service."""
    return SimpleNamespace(get=lambda employee_id: None)


@pytest.mark.parametrize("value, enabled", [("true", True), (" TRUE ", True), ("false", False), ("", False)])
def test_tracing_status_reads_environment(monkeypatch, value, enabled):
    monkeypatch.setenv("LANGSMITH_TRACING", value)
    assert _tracing_enabled() is enabled
    assert os.environ["LANGSMITH_TRACING"] == value


def test_tracing_status_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    assert not _tracing_enabled()


def test_text_content_blocks():
    assert _content_as_text([{"type": "text", "text": "Hello"}, {"type": "text", "text": "there"}]) == "Hello\nthere"


def test_empty_model_answer_uses_fallback(tmp_path):
    class EmptyAgent:
        def invoke(self, state, config=None, context=None):
            return {"messages": [*state["messages"], AIMessage(content="")]}

    service = ChatService(EmptyAgent(), ConversationStore(tmp_path / "m.sqlite3"))
    thread_id = service.start_conversation("E104")
    turn = service.send(thread_id, "E104", "Hello")
    assert "try again" in turn["answer"]


def test_chat_starters_settings_reset_and_no_trace_panels(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("HELPDESK_MEMORY_DATABASE_PATH", str(tmp_path / "memory.sqlite3"))

    class FakeAgent:
        def get_state(self, config):
            return SimpleNamespace(interrupts=())

        def invoke(self, state, config=None, context=None):
            return {"messages": [*state["messages"], AIMessage(content="INC-1042 is in progress.")]}

    service = ChatService(FakeAgent(), ConversationStore(tmp_path / "memory.sqlite3"))
    monkeypatch.setattr("streamlit_app._build_runtime", lambda *args: service)
    monkeypatch.setattr("streamlit_app.list_helpdesk_prompts", lambda url, secret: [])  # offline
    monkeypatch.setattr("streamlit_app._profiles", _no_profiles)
    # Import the module inside the test app so runtime monkeypatches are shared.
    app = AppTest.from_string("from streamlit_app import main\nmain()\n").run()
    assert not app.exception
    assert app.title[0].value == "Enterprise Helpdesk Agent"
    assert not app.tabs
    assert any("LangSmith tracing: disabled" in element.value for element in app.caption)
    assert not any("Turn trace" in element.label for element in app.expander)
    assert [button.label for button in app.main.button] == ["Ticket status", "My tickets", "Leave balance"]

    next(button for button in app.button if button.label == "Ticket status").click().run()
    assert not app.exception
    assert len(app.chat_message) == 2
    assert service.store.get_messages(app.session_state["thread_id"], "E104")[1]["content"] == "INC-1042 is in progress."

    app.chat_input[0].set_value("What about its priority?").run()
    assert len(app.chat_message) == 4

    app.sidebar.text_input[0].set_value("E105").run()
    assert not app.session_state["thread_id"]
    assert len(app.chat_message) == 0

    next(button for button in app.button if button.label == "My tickets").click().run()
    next(button for button in app.button if "New conversation" in button.label).click().run()
    assert not app.session_state["thread_id"]
    assert not app.exception


def test_real_entrypoint_renders(monkeypatch, tmp_path, mcp_service):
    # The real app discovers its tools from the MCP service, so point it at the test one.
    settings = mcp_service.settings
    monkeypatch.setenv("HELPDESK_MCP_URL", settings.mcp_url)
    monkeypatch.setenv("HELPDESK_MCP_SECRET", settings.mcp_secret)
    monkeypatch.setenv("HELPDESK_MEMORY_DATABASE_PATH", str(tmp_path / "memory.sqlite3"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py")).run()
    assert not app.exception
    assert app.chat_input


def test_unreachable_mcp_server_shows_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setenv("HELPDESK_MEMORY_DATABASE_PATH", str(tmp_path / "memory.sqlite3"))

    def unreachable(*args):
        raise McpSetupError("Cannot load tools from the helpdesk MCP server at http://x/mcp.")

    monkeypatch.setattr("streamlit_app._build_runtime", unreachable)
    app = AppTest.from_string("from streamlit_app import main\nmain()\n").run()

    assert not app.exception
    assert "helpdesk MCP server" in app.error[0].value
    assert not app.chat_input


def _expired_key_error() -> AuthenticationError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return AuthenticationError(
        "Your API key has expired.", response=httpx.Response(401, request=request), body=None
    )


@pytest.mark.parametrize(
    "failure, shown",
    [
        (_expired_key_error(), "Update OPENAI_API_KEY in your .env file"),
        (RuntimeError("provider exploded"), "helpdesk MCP server is running"),
    ],
)
def test_failed_turn_explains_the_cause_and_logs_the_details(monkeypatch, tmp_path, caplog, failure, shown):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("HELPDESK_MEMORY_DATABASE_PATH", str(tmp_path / "memory.sqlite3"))

    class FailingAgent:
        def get_state(self, config):
            return SimpleNamespace(interrupts=())

        def invoke(self, state, config=None, context=None):
            raise failure

    service = ChatService(FailingAgent(), ConversationStore(tmp_path / "memory.sqlite3"))
    monkeypatch.setattr("streamlit_app._build_runtime", lambda *args: service)
    monkeypatch.setattr("streamlit_app.list_helpdesk_prompts", lambda url, secret: [])  # offline
    monkeypatch.setattr("streamlit_app._profiles", _no_profiles)

    with caplog.at_level(logging.ERROR):
        app = AppTest.from_string("from streamlit_app import main\nmain()\n").run()
        app.chat_input[0].set_value("What's the status of INC-1042?").run()

    assert not app.exception
    assert shown in app.error[0].value
    assert str(failure) not in app.error[0].value  # details stay out of the UI...
    assert str(failure) in caplog.text  # ...but reach the server log


class _RecordingAgent:
    """Answers every turn, remembers the text the model was sent, and can report a paused write."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.interrupts: tuple = ()

    def get_state(self, config):
        return SimpleNamespace(interrupts=self.interrupts)

    def invoke(self, state, config=None, context=None):
        self.sent.append(state["messages"][0].content)
        return {"messages": [*state["messages"], AIMessage(content="Done.")]}


def _prompt_app(monkeypatch, tmp_path, url, secret):
    """The real app with a recording agent, pointed at the given MCP service."""
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("HELPDESK_MEMORY_DATABASE_PATH", str(tmp_path / "memory.sqlite3"))
    monkeypatch.setenv("HELPDESK_MCP_URL", url)
    monkeypatch.setenv("HELPDESK_MCP_SECRET", secret)
    agent = _RecordingAgent()
    service = ChatService(agent, ConversationStore(tmp_path / "memory.sqlite3"))
    monkeypatch.setattr("streamlit_app._build_runtime", lambda *args: service)
    app = AppTest.from_string("from streamlit_app import main\nmain()\n").run()
    assert not app.exception
    return app, agent, service


def _use_template(app, title, values):
    """Pick a template, fill its fields and submit in one run, as a browser form does."""
    next(s for s in app.sidebar.selectbox if s.label == "Template").select(title).run()
    for label, value in values.items():
        next(t for t in app.sidebar.text_input if t.label == label).set_value(value)
    next(b for b in app.sidebar.button if b.label == "Use template").click().run()


def test_prompt_template_runs_a_turn_with_a_short_transcript_entry(monkeypatch, tmp_path, mcp_service):
    fetched = []

    def counting(url, secret):
        fetched.append(url)
        return list_helpdesk_prompts(url, secret)

    monkeypatch.setattr("streamlit_app.list_helpdesk_prompts", counting)
    settings = mcp_service.settings
    app, agent, service = _prompt_app(monkeypatch, tmp_path, settings.mcp_url, settings.mcp_secret)
    template = next(s for s in app.sidebar.selectbox if s.label == "Template")
    assert {"Raise an IT ticket", "Leave overview"} <= set(template.options)

    _use_template(
        app,
        "Raise an IT ticket",
        {"issue": "VPN drops every ten minutes", "category (optional)": "VPN"},
    )

    assert not app.exception
    assert "Employee problem: VPN drops every ten minutes" in agent.sent[0]
    assert "create_ticket" in agent.sent[0]
    label = "Raise an IT ticket: issue=VPN drops every ten minutes, category=VPN"
    transcript = service.store.get_messages(app.session_state["thread_id"], "E104")
    assert [m["content"] for m in transcript] == [label, "Done."]
    assert app.chat_message[0].markdown[0].value == label
    assert len(fetched) == 1  # the catalog is fetched once per browser session


def test_prompt_template_asks_for_missing_required_values(monkeypatch, tmp_path, mcp_service):
    settings = mcp_service.settings
    app, agent, _ = _prompt_app(monkeypatch, tmp_path, settings.mcp_url, settings.mcp_secret)

    _use_template(app, "Raise an IT ticket", {})

    assert [e.value for e in app.sidebar.error] == ["Fill in: issue"]
    assert agent.sent == []
    assert len(app.chat_message) == 0


def test_prompt_template_waits_while_an_approval_is_pending(monkeypatch, tmp_path, mcp_service):
    settings = mcp_service.settings
    app, agent, _ = _prompt_app(monkeypatch, tmp_path, settings.mcp_url, settings.mcp_secret)
    app.chat_input[0].set_value("Raise a ticket for wifi dropping.").run()
    draft = {
        "title": "Wifi dropping",
        "description": "The wifi keeps dropping.",
        "category": "Network",
        "priority": "medium",
    }
    agent.interrupts = (
        SimpleNamespace(value={"action_requests": [{"name": "create_ticket", "args": draft}]}),
    )
    app.run()

    _use_template(app, "Leave overview", {})

    assert any("Approve or reject" in w.value for w in app.warning)
    assert agent.sent == ["Raise a ticket for wifi dropping."]


def test_prompt_templates_are_unavailable_without_the_server(monkeypatch, tmp_path):
    app, _, _ = _prompt_app(monkeypatch, tmp_path, "http://127.0.0.1:9/mcp", "x" * 32)

    assert any("Cannot list prompts" in c.value for c in app.sidebar.caption)
    assert not any(s.label == "Template" for s in app.sidebar.selectbox)
    assert app.chat_input


def _summary(profile) -> str:
    return f"{profile.full_name} · {profile.department} · {profile.office_location}"


def test_sidebar_shows_the_signed_in_employees_profile(monkeypatch, tmp_path, mcp_service):
    settings = mcp_service.settings
    app, _, _ = _prompt_app(monkeypatch, tmp_path, settings.mcp_url, settings.mcp_secret)
    asha = _summary(mcp_service.repository.get_my_profile("E104"))
    luis = _summary(mcp_service.repository.get_my_profile("E105"))

    assert asha in [c.value for c in app.sidebar.caption]

    app.sidebar.text_input[0].set_value("E105").run()

    captions = [c.value for c in app.sidebar.caption]
    assert luis in captions
    assert asha not in captions


def test_sidebar_still_works_for_an_employee_without_a_profile(monkeypatch, tmp_path, mcp_service):
    settings = mcp_service.settings
    app, _, _ = _prompt_app(monkeypatch, tmp_path, settings.mcp_url, settings.mcp_secret)
    asha = _summary(mcp_service.repository.get_my_profile("E104"))

    app.sidebar.text_input[0].set_value("E999").run()

    assert not app.exception
    assert asha not in [c.value for c in app.sidebar.caption]
    assert app.chat_input