"""Focused helpdesk chat; execution tracing is managed by LangSmith."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from config import Settings, get_settings
from data.repository import HelpdeskRepository
from graph.agent import build_agent


STYLES = """
<style>
  .stApp { background: #f6f8fc; color: #172b4d; }
    [data-testid="stMainBlockContainer"] { max-width: 960px; padding-top: 2.5rem; }
  [data-testid="stMain"] h1, [data-testid="stMain"] h2,
  [data-testid="stMain"] h3, [data-testid="stMain"] p,
  [data-testid="stMain"] li, [data-testid="stMain"] label { color: #172b4d; }
  [data-testid="stCaptionContainer"] { color: #566780; }
  [data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e4eaf3; }
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3, [data-testid="stSidebar"] label { color: #172b4d; }
  [data-testid="stSidebar"] input { background: #f6f8fc; color: #172b4d; }
  [data-testid="stSidebar"] [data-testid="stExpander"] { background: #f8faff; }
  .brand { color: #4966db; font-weight: 800; font-size: 1.3rem; letter-spacing: -.04em; }
    [data-testid="stMain"] h1 { font-size: clamp(1.7rem, 4vw, 2.4rem);
        letter-spacing: -.04em; font-weight: 750; }
  .stButton > button, .stLinkButton > a { border-radius: 12px; }
  [data-testid="stMain"] .stButton > button { background: #fff; border: 1px solid #dde5f1;
    min-height: 3.4rem; color: #253d64; }
  [data-testid="stMain"] .stButton > button:hover { border-color: #6c80e8; background: #eff3ff; }
  [data-testid="stChatMessage"] { background: #fff; border: 1px solid #e4eaf3;
    border-radius: 18px; padding: 1.25rem; margin-bottom: 1rem; }
  [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { color: #172b4d; }
  [data-testid="stChatInput"] { border: 1px solid #d8e1f1; border-radius: 16px; background: #fff; }
  [data-testid="stChatInputTextArea"] { color: #172b4d; background: #fff; caret-color: #4966db; }
  [data-testid="stChatInputTextArea"]::placeholder { color: #66758e; opacity: 1; }
  [data-testid="stBottomBlockContainer"] { background: #f6f8fc; }
  @media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] { padding-top: 1rem; }
  }
</style>
"""


@st.cache_resource(show_spinner=False)
def _build_runtime(database_path: str, employee_id: str, model_name: str, max_model_steps: int):
    settings = Settings(Path(database_path), employee_id, model_name, max_model_steps)
    return build_agent(settings, HelpdeskRepository(settings.database_path))


def _content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(part["text"])
            for part in content
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ]
        return "\n".join(parts) if parts else json.dumps(content, ensure_ascii=False, default=str)
    return str(content)


def _run_turn(agent: Any, prior_messages: list[Any], prompt: str) -> tuple[str, list[Any]]:
    """Invoke normally so LangSmith owns tracing, not a second UI event collector."""
    result = agent.invoke({"messages": [*prior_messages, HumanMessage(content=prompt)]})
    messages = list(result["messages"])
    if messages and isinstance(messages[-1], AIMessage) and not messages[-1].tool_calls:
        answer = _content_as_text(messages[-1].content)
    else:
        answer = ""
    return answer or "I couldn't complete that request. Please try again.", messages


def _tracing_enabled() -> bool:
    """Report configuration only; do not change tracing or imply connectivity."""
    return os.getenv("LANGSMITH_TRACING", "").strip().lower() == "true"


def _clear_conversation() -> None:
    st.session_state["agent_messages"] = []
    st.session_state["conversation"] = []


def main() -> None:
    st.set_page_config(page_title="Enterprise Helpdesk Agent", page_icon="🎫", layout="wide")
    st.markdown(STYLES, unsafe_allow_html=True)
    defaults = get_settings()
    tracing = _tracing_enabled()

    with st.sidebar:
        st.markdown('<div class="brand">Acme Corp</div>', unsafe_allow_html=True)
        st.divider()
        employee_id = st.text_input("Demo employee ID", value=defaults.employee_id).strip().upper()
        st.caption("Mock identity · not authentication")
        st.button("New conversation", on_click=_clear_conversation, use_container_width=True)
        with st.expander("Advanced settings"):
            model_name = st.text_input("Chat model", value=defaults.model_name).strip()
            database_path = st.text_input("SQLite database", value=str(defaults.database_path)).strip()
            max_model_steps = st.slider(
                "Maximum model calls per turn", min_value=1, max_value=12,
                value=min(defaults.max_model_steps, 12),
            )
            st.caption("Changing settings clears the conversation.")
            st.caption(f"LangSmith tracing: {'enabled' if tracing else 'disabled'} via LANGSMITH_TRACING.")
            if tracing:
                st.caption("Conversation and tool data may be sent to LangSmith.")
                st.link_button("Open LangSmith", "https://smith.langchain.com/", use_container_width=True)

    signature = (employee_id, model_name, database_path, max_model_steps)
    if st.session_state.get("settings_signature", signature) != signature:
        _clear_conversation()
    st.session_state["settings_signature"] = signature
    st.session_state.setdefault("agent_messages", [])
    st.session_state.setdefault("conversation", [])

    st.title("Enterprise Helpdesk Agent")
    st.caption("Acme Corp · Ticket status, your tickets, and leave balances. Read-only mock data.")

    suggested_prompt = None
    if not st.session_state["conversation"]:
        for column, label, question in zip(
            st.columns(3),
            ("Ticket status", "My tickets", "Leave balance"),
            ("What's the status of INC-1042?", "List my tickets", "How many leave days do I have?"),
        ):
            if column.button(label, use_container_width=True):
                suggested_prompt = question

    for turn in st.session_state["conversation"]:
        with st.chat_message("user", avatar="👤"):
            st.markdown(turn["prompt"])
        with st.chat_message("assistant", avatar="🤖"):
            if turn.get("error"):
                st.error(turn["answer"])
            else:
                st.markdown(turn["answer"])

    typed_prompt = st.chat_input("Ask about a ticket or your leave balance…")
    prompt = typed_prompt or suggested_prompt
    if not prompt:
        return

    with st.container():
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🤖"):
            try:
                if not employee_id or not model_name:
                    raise ValueError("Set a demo employee ID and chat model in the sidebar.")
                if not Path(database_path).is_file():
                    raise ValueError("The helpdesk database was not found. Check the path in Advanced settings.")
                if not os.getenv("OPENAI_API_KEY"):
                    raise ValueError("OPENAI_API_KEY is not configured. Add it to your environment and restart the app.")
                with st.spinner("Checking your helpdesk records…"):
                    agent = _build_runtime(database_path, employee_id, model_name, max_model_steps)
                    answer, messages = _run_turn(agent, st.session_state["agent_messages"], prompt)
                st.session_state["agent_messages"] = messages
                st.session_state["conversation"].append({"prompt": prompt, "answer": answer})
            except Exception:
                # Provider exceptions can contain request details; keep them out of the UI.
                answer = "We couldn't complete your request. Check your model, credentials, and database settings, then try again."
                if not employee_id or not model_name:
                    answer = "Set a demo employee ID and chat model in the sidebar, then try again."
                elif not Path(database_path).is_file():
                    answer = "The helpdesk database was not found. Check the path in Advanced settings."
                elif not os.getenv("OPENAI_API_KEY"):
                    answer = "OPENAI_API_KEY is not configured. Add it to your environment and restart the app."
                st.session_state["conversation"].append({"prompt": prompt, "answer": answer, "error": True})
    st.rerun()


if __name__ == "__main__":
    main()