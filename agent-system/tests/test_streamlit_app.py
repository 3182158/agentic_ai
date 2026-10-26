"""UI regressions without provider calls or external tracing."""

import os
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from streamlit.testing.v1 import AppTest

from streamlit_app import _content_as_text, _run_turn, _tracing_enabled


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


def test_empty_model_answer_uses_fallback():
    class EmptyAgent:
        def invoke(self, state):
            return {"messages": [*state["messages"], AIMessage(content="")]}

    answer, messages = _run_turn(EmptyAgent(), [], "Hello")
    assert "try again" in answer
    assert isinstance(messages[0], HumanMessage)


def test_chat_starters_settings_reset_and_no_trace_panels(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")

    class FakeAgent:
        def invoke(self, state):
            return {"messages": [*state["messages"], AIMessage(content="INC-1042 is in progress.")]}

    monkeypatch.setattr("streamlit_app._build_runtime", lambda *args: FakeAgent())
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
    assert app.session_state["conversation"][0]["answer"] == "INC-1042 is in progress."

    app.chat_input[0].set_value("What about its priority?").run()
    assert len(app.chat_message) == 4
    assert len(app.session_state["agent_messages"]) == 4

    app.sidebar.text_input[0].set_value("E105").run()
    assert not app.session_state["conversation"]
    assert len(app.chat_message) == 0

    next(button for button in app.button if button.label == "My tickets").click().run()
    next(button for button in app.button if "New conversation" in button.label).click().run()
    assert not app.session_state["conversation"]
    assert not app.exception


def test_real_entrypoint_renders():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py")).run()
    assert not app.exception
    assert app.chat_input