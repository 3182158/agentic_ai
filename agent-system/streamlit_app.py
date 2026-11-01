"""Focused helpdesk chat; execution tracing is managed by LangSmith."""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, get_args

import streamlit as st
from openai import AuthenticationError

from config import get_settings
from domain import LeaveType, TicketCategory, TicketPriority
from agents.agent import build_agent
from memory.checkpointer import create_checkpointer
from memory.long_term import LongTermMemory
from memory.service import ChatService, content_as_text as _content_as_text
from memory.store import ConversationNotFound, ConversationStore
from tools.mcp_client import (
    EmployeeProfiles,
    McpPromptError,
    McpSetupError,
    get_helpdesk_prompt,
    list_helpdesk_prompts,
    prompt_label,
)

logger = logging.getLogger(__name__)


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
def _build_runtime(
    employee_id: str, model_name: str, max_model_steps: int, memory_path: str
) -> ChatService:
    settings = replace(
        get_settings(),
        employee_id=employee_id,
        model_name=model_name,
        max_model_steps=max_model_steps,
        memory_database_path=Path(memory_path),
    )
    agent = build_agent(
        settings,
        checkpointer=create_checkpointer(settings.memory_database_path),
        long_term_memory=LongTermMemory(settings.memory_database_path),
    )
    return ChatService(agent, ConversationStore(settings.memory_database_path))


@st.cache_resource(show_spinner=False)
def _profiles(url: str, secret: str) -> EmployeeProfiles:
    return EmployeeProfiles(url, secret)


def _tracing_enabled() -> bool:
    """Report configuration only; do not change tracing or imply connectivity."""
    return os.getenv("LANGSMITH_TRACING", "").strip().lower() == "true"


def _clear_conversation() -> None:
    st.session_state["thread_id"] = None


def _open_conversation(thread_id: str) -> None:
    st.session_state["thread_id"] = thread_id


def _render_sidebar_history(service: ChatService, user_id: str) -> None:
    store = service.store
    st.subheader("Conversations")
    query = st.text_input("Search conversations", key="search_query").strip()
    if query:
        seen: set[str] = set()
        for hit in store.search(user_id, query):
            if hit["thread_id"] in seen:
                continue
            seen.add(hit["thread_id"])
            st.button(
                hit["title"], key=f"hit-{hit['thread_id']}", use_container_width=True,
                on_click=_open_conversation, args=(hit["thread_id"],),
            )
        if not seen:
            st.caption("No matches.")
    else:
        for conversation in store.list_conversations(user_id):
            st.button(
                conversation["title"], key=f"conv-{conversation['thread_id']}",
                use_container_width=True, on_click=_open_conversation,
                args=(conversation["thread_id"],),
            )
    with st.expander("Your usage"):
        stats = store.analytics(user_id)
        st.caption(
            f"{stats['conversations']} conversations · {stats['user_messages']} questions"
        )
        if stats["tool_usage"]:
            st.caption("Tools: " + ", ".join(f"{n} ×{c}" for n, c in stats["tool_usage"].items()))


def _select(label: str, options: list[str], current: object, default: int = 0) -> str:
    return st.selectbox(
        label, options, index=options.index(current) if current in options else default
    )


def _render_approval(service: ChatService, user_id: str, pending: dict[str, Any]) -> None:
    """Show the drafted write action; nothing is written until the user approves."""
    args = pending["args"]
    action = pending["name"]
    thread_id = st.session_state["thread_id"]
    with st.chat_message("assistant", avatar="🤖"):
        if action == "apply_leave":
            st.markdown("**Approval required: submit this leave request?**")
        else:
            st.markdown("**Approval required: create this ticket?**")
        with st.form("write_approval"):
            if action == "apply_leave":
                edited = {
                    "leave_type": _select("Leave type", list(get_args(LeaveType)), args.get("leave_type")),
                    "start_date": st.text_input("Start date (YYYY-MM-DD)", value=args.get("start_date", "")).strip(),
                    "end_date": st.text_input("End date (YYYY-MM-DD)", value=args.get("end_date", "")).strip(),
                    "reason": st.text_area("Reason", value=args.get("reason", "")).strip(),
                }
            else:
                edited = {
                    "title": st.text_input("Title", value=args.get("title", "")).strip(),
                    "description": st.text_area("Description", value=args.get("description", "")).strip(),
                    "category": _select("Category", list(get_args(TicketCategory)), args.get("category")),
                    "priority": _select("Priority", list(get_args(TicketPriority)), args.get("priority"), 1),
                }
            approve = st.form_submit_button("Approve and submit", type="primary")
            reject = st.form_submit_button("Reject")
    if not (approve or reject):
        return
    try:
        if reject:
            service.resume(thread_id, user_id, "reject")
        else:
            service.resume(thread_id, user_id, "approve" if edited == args else "edit", edited)
    except Exception:
        logger.exception("Approval could not be completed")
        service.store.add_message(
            thread_id, user_id, "assistant",
            "We couldn't complete the approval. Check the fields and try again.",
            is_error=True,
        )
    st.rerun()


def _render_prompt_picker(url: str, secret: str) -> tuple[str, str] | None:
    """Offer the MCP server's prompt templates; returns (transcript label, text) once one is used."""
    with st.expander("Prompt templates"):
        catalog = f"prompt_catalog:{url}"  # fetched once per browser session; reload to refresh
        if catalog not in st.session_state:
            try:
                st.session_state[catalog] = list_helpdesk_prompts(url, secret)
            except McpPromptError as exc:
                st.caption(str(exc))
                return None
        prompts = {p.name: p for p in st.session_state[catalog]}
        if not prompts:
            st.caption("The helpdesk server offers no prompt templates.")
            return None
        name = st.selectbox("Template", list(prompts), format_func=lambda n: prompts[n].title or n)
        prompt = prompts[name]
        if prompt.description:
            st.caption(prompt.description)
        with st.form(f"prompt-form-{name}"):
            values = {
                a.name: st.text_input(
                    a.name + ("" if a.required else " (optional)"), help=a.description
                ).strip()
                for a in prompt.arguments or []
            }
            submitted = st.form_submit_button("Use template")
        if not submitted:
            return None
        given = {key: value for key, value in values.items() if value}
        missing = [a.name for a in prompt.arguments or [] if a.required and a.name not in given]
        if missing:
            st.error(f"Fill in: {', '.join(missing)}")
            return None
        try:
            return prompt_label(prompt, given), get_helpdesk_prompt(url, secret, name, given)
        except McpPromptError as exc:
            st.error(str(exc))
            return None


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
        profiles = _profiles(defaults.mcp_url, defaults.mcp_secret)
        if profile := (profiles.get(employee_id) if employee_id else None):
            st.caption(profile.summary())
        st.button("New conversation", on_click=_clear_conversation, use_container_width=True)
        with st.expander("Advanced settings"):
            model_name = st.text_input("Chat model", value=defaults.model_name).strip()
            memory_path = st.text_input(
                "Chat memory database", value=str(defaults.memory_database_path)
            ).strip()
            max_model_steps = st.slider(
                "Maximum model calls per turn", min_value=1, max_value=12,
                value=min(defaults.max_model_steps, 12),
            )
            st.caption("Changing settings starts a new conversation.")
            st.caption(f"LangSmith tracing: {'enabled' if tracing else 'disabled'} via LANGSMITH_TRACING.")
            if tracing:
                st.caption("Conversation and tool data may be sent to LangSmith.")
                st.link_button("Open LangSmith", "https://smith.langchain.com/", use_container_width=True)

    signature = (employee_id, model_name, memory_path, max_model_steps)
    if st.session_state.get("settings_signature", signature) != signature:
        _clear_conversation()
    st.session_state["settings_signature"] = signature
    st.session_state.setdefault("thread_id", None)

    service: ChatService | None = None
    template: tuple[str, str] | None = None
    if employee_id and memory_path:
        try:
            service = _build_runtime(employee_id, model_name, max_model_steps, memory_path)
        except McpSetupError as exc:
            st.error(str(exc))
            st.stop()
        with st.sidebar:
            template = _render_prompt_picker(defaults.mcp_url, defaults.mcp_secret)
            _render_sidebar_history(service, employee_id)

    transcript: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    if service and st.session_state["thread_id"]:
        try:
            transcript = service.store.get_messages(st.session_state["thread_id"], employee_id)
            pending = service.pending_approval(st.session_state["thread_id"], employee_id)
        except ConversationNotFound:
            _clear_conversation()

    st.title("Enterprise Helpdesk Agent")
    st.caption("Acme Corp · Ticket status, your tickets, leave balance, history, and ticket or leave requests with your approval.")

    suggested_prompt = None
    if not transcript:
        for column, label, question in zip(
            st.columns(3),
            ("Ticket status", "My tickets", "Leave balance"),
            ("What's the status of INC-1042?", "List my tickets", "How many leave days do I have?"),
        ):
            if column.button(label, use_container_width=True):
                suggested_prompt = question

    for message in transcript:
        with st.chat_message(message["role"], avatar="👤" if message["role"] == "user" else "🤖"):
            if message["is_error"]:
                st.error(message["content"])
                continue
            st.markdown(message["content"])

    if pending:
        if template:
            st.warning("Approve or reject the pending request before using a template.")
        _render_approval(service, employee_id, pending)
        return

    typed_prompt = st.chat_input("Ask about a ticket or your leave balance…")
    prompt = typed_prompt or suggested_prompt
    model_text = None
    if not prompt and template:
        prompt, model_text = template
    if not prompt:
        return

    with st.container():
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🤖"):
            try:
                if not employee_id or not model_name:
                    raise ValueError("Set a demo employee ID and chat model in the sidebar.")
                if not os.getenv("OPENAI_API_KEY"):
                    raise ValueError("OPENAI_API_KEY is not configured. Add it to your environment and restart the app.")
                if not st.session_state["thread_id"]:
                    st.session_state["thread_id"] = service.start_conversation(employee_id)
                with st.spinner("Checking your helpdesk records…"):
                    thread_id = st.session_state["thread_id"]
                    if model_text:
                        service.send(thread_id, employee_id, model_text, display=prompt)
                    else:
                        service.send(thread_id, employee_id, prompt)
            except Exception as exc:
                # Provider exceptions can contain request details; log them, keep them out of the UI.
                logger.exception("Chat turn failed")
                answer = "We couldn't complete your request. Check your model and credentials, and that the helpdesk MCP server is running, then try again."
                if not employee_id or not model_name:
                    answer = "Set a demo employee ID and chat model in the sidebar, then try again."
                elif not os.getenv("OPENAI_API_KEY"):
                    answer = "OPENAI_API_KEY is not configured. Add it to your environment and restart the app."
                elif isinstance(exc, AuthenticationError):
                    answer = "OpenAI rejected the API key (it may have expired). Update OPENAI_API_KEY in your .env file and restart the app."
                if service:
                    if not st.session_state["thread_id"]:
                        st.session_state["thread_id"] = service.start_conversation(employee_id)
                    service.record_error(st.session_state["thread_id"], employee_id, prompt, answer)
    st.rerun()


if __name__ == "__main__":
    main()