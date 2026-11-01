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
from tools.mcp_client import McpSetupError


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

    with caplog.at_level(logging.ERROR):
        app = AppTest.from_string("from streamlit_app import main\nmain()\n").run()
        app.chat_input[0].set_value("What's the status of INC-1042?").run()

    assert not app.exception
    assert shown in app.error[0].value
    assert str(failure) not in app.error[0].value  # details stay out of the UI...
    assert str(failure) in caplog.text  # ...but reach the server log