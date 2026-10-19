"""Browser UI for the LangGraph helpdesk agent and its execution trace."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from config import Settings, get_settings
from data.repository import HelpdeskRepository
from graph.agent import build_agent


st.set_page_config(
    page_title="Acme Helpdesk Agent",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
            .stApp { background: radial-gradient(ellipse at 50% -20%, #eaf2ff 0, #f7f9fc 42%, #f7f9fc 100%); color: #172337; }
            [data-testid="stMain"] { color: #172337; }
            [data-testid="stMain"] [data-testid="stMarkdownContainer"],
            [data-testid="stMain"] [data-testid="stMetricLabel"],
            [data-testid="stMain"] [data-testid="stMetricValue"],
            [data-testid="stMain"] [data-testid="stCaptionContainer"],
            [data-testid="stMain"] [data-testid="stWidgetLabel"] { color: #172337 !important; }
            [data-testid="stMain"] [data-testid="stCaptionContainer"] { color: #526176 !important; }
      [data-testid="stSidebar"] { background: #101a2b; }
      [data-testid="stSidebar"] * { color: #eef3ff; }
            [data-testid="stSidebar"] input { background: #f8fafc !important; color: #152033 !important; caret-color: #152033; }
            [data-testid="stSidebar"] input::placeholder { color: #58677d !important; opacity: 1; }
            [data-testid="stChatInputTextArea"] { background: #fff !important; color: #172337 !important; caret-color: #172337; }
            [data-testid="stChatInputTextArea"]::placeholder { color: #526176 !important; opacity: 1; }
            [data-testid="stChatMessage"] { color: #172337; }
            [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { color: #172337 !important; }
      .hero { padding: 1.35rem 1.6rem; border: 1px solid #dce5f2; border-radius: 18px;
        background: linear-gradient(115deg, #fff 5%, #f0f5ff 100%); margin-bottom: 1rem; }
      .hero-kicker { color: #536d9b; font-size: .78rem; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; }
      .hero-title { color: #14233b; font-size: 2rem; font-weight: 750; margin: .2rem 0; }
      .hero-copy { color: #536176; margin: 0; }
      div[data-testid="stMetric"] { background: white; border: 1px solid #e1e8f2; padding: .8rem 1rem; border-radius: 14px; }
      .trust-note { border-left: 4px solid #5b8def; padding: .65rem .9rem; background: #eef4ff; border-radius: 5px; color: #354764; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def _build_runtime(database_path: str, employee_id: str, model_name: str, max_model_steps: int):
    settings = Settings(
        database_path=Path(database_path),
        employee_id=employee_id,
        model_name=model_name,
        max_model_steps=max_model_steps,
    )
    repository = HelpdeskRepository(settings.database_path)
    return build_agent(settings, repository)


def _content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            str(part["text"])
            for part in content
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ]
        return "\n".join(text_parts) if text_parts else json.dumps(content, ensure_ascii=False, default=str)
    return str(content)


def _pretty_json(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _trace_turn(
    agent: Any,
    prior_messages: list[Any],
    prompt: str,
    on_graph_event: Any | None = None,
) -> tuple[str, list[dict[str, Any]], list[Any]]:
    turn_messages: list[Any] = []
    trace: list[dict[str, Any]] = []
    final_answer = ""
    completed_nodes: set[str] = set()
    active_node: str | None = "assistant"
    if on_graph_event:
        on_graph_event(active_node, completed_nodes, "Starting at assistant node…")

    stream = agent.stream(
        {"messages": [*prior_messages, HumanMessage(content=prompt)], "model_steps": 0},
        stream_mode=["updates", "tasks"],
    )
    for item in stream:
        if isinstance(item, tuple) and len(item) == 2:
            stream_kind, update = item
        else:
            stream_kind, update = "updates", item

        if stream_kind == "tasks":
            task_name = update.get("name") if isinstance(update, dict) else None
            if task_name in {"assistant", "tools", "step_limit"}:
                # Task events with an input indicate that the node has started.
                if "input" in update and "result" not in update:
                    active_node = task_name
                    if on_graph_event:
                        on_graph_event(active_node, completed_nodes, f"Running {task_name.replace('_', ' ')} node…")
                elif "result" in update:
                    completed_nodes.add(task_name)
                    active_node = None
                    if on_graph_event:
                        on_graph_event(None, completed_nodes, f"Completed {task_name.replace('_', ' ')} node.")
            continue

        if not isinstance(update, dict):
            continue
        for node_name, node_update in update.items():
            if node_name in {"assistant", "tools", "step_limit"}:
                completed_nodes.add(node_name)
                active_node = None
                if on_graph_event:
                    on_graph_event(None, completed_nodes, f"Completed {node_name.replace('_', ' ')} node.")
            for message in node_update.get("messages", []):
                turn_messages.append(message)
                if isinstance(message, AIMessage) and message.tool_calls:
                    for tool_call in message.tool_calls:
                        trace.append(
                            {
                                "kind": "tool_request",
                                "title": f"Model requested {tool_call['name']}",
                                "description": "A typed, read-only tool call selected by the model.",
                                "tool": tool_call["name"],
                                "payload": tool_call.get("args", {}),
                            }
                        )
                elif isinstance(message, ToolMessage):
                    trace.append(
                        {
                            "kind": "tool_result",
                            "title": f"Tool result · {message.name or 'helpdesk tool'}",
                            "description": "Returned by the local SQLite repository through the tool boundary.",
                            "tool": message.name or "helpdesk tool",
                            "payload": message.content,
                        }
                    )
                elif isinstance(message, AIMessage):
                    final_answer = _content_as_text(message.content)
                    trace.append(
                        {
                            "kind": "model_response",
                            "title": "Agent response",
                            "description": "The model produced a user-facing answer from the conversation and tool results.",
                            "payload": final_answer,
                        }
                    )
    completed_nodes.add("END")
    active_node = None
    if on_graph_event:
        on_graph_event(None, completed_nodes, "Workflow reached END.")
    return final_answer or "I couldn't complete that request. Please try again.", trace, turn_messages


def _render_trace(trace: list[dict[str, Any]]) -> None:
    if not trace:
        st.caption("No intermediate tool activity was recorded for this turn.")
        return
    for index, event in enumerate(trace, start=1):
        with st.container(border=True):
            heading, badge = st.columns([5, 1])
            heading.markdown(f"**{index}. {event['title']}**")
            badge.caption(event["kind"].replace("_", " ").title())
            st.caption(event["description"])
            if "tool" in event:
                st.caption(f"Tool: `{event['tool']}`")
            st.code(_pretty_json(event.get("payload", "")), language="json")


def _render_explainer(employee_id: str, model_name: str, max_model_steps: int) -> None:
    st.subheader("One request, visible end to end")
    st.write(
        "This app runs the same LangGraph workflow as the command-line demo. It does not expose hidden model reasoning; "
        "instead, it shows observable events: tool requests, arguments, tool results, and the final answer."
    )

    stages = [
        ("01 · Message", "Your question and recent chat history are sent to the agent. The app supplies the demo identity separately."),
        ("02 · Assistant node", f"LangGraph calls **{model_name}** with the helpdesk instructions and typed tool definitions."),
        ("03 · Tool decision", "The model may request a read-only tool. If no tool is needed, its answer ends the turn. The loop is capped at {0} model calls.".format(max_model_steps)),
        ("04 · Tool node", "LangGraph executes the requested function. Employee scope is closed over by the application; the model cannot pass a different employee ID."),
        ("05 · Repository", "A parameterized, read-only SQLite query returns structured ticket or leave data. The result is added to the conversation."),
        ("06 · Response", "The assistant uses the tool observation to answer. Conversation and traces stay in this browser session only."),
    ]
    cols = st.columns(3)
    for index, (title, description) in enumerate(stages):
        with cols[index % 3]:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(description)

    st.markdown("#### Agent execution graph")
    graph_preview = st.empty()
    graph_note = st.empty()
    _render_live_graph(
        graph_preview,
        graph_note,
        None,
        {"START", "END"},
        "Green nodes are completed; amber indicates the active node.",
    )

    st.markdown("#### Available read-only tools")
    st.dataframe(
        [
            {"Tool": "get_ticket_status", "Purpose": "Look up status, priority, assignee, title, and update time for a ticket you may access."},
            {"Tool": "list_my_tickets", "Purpose": "List tickets belonging to the configured demo employee."},
            {"Tool": "check_leave_balance", "Purpose": "Read annual, sick, carry-forward, and total leave balance for the configured demo employee."},
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.markdown(
        f'<div class="trust-note"><b>Current demo identity:</b> {employee_id}. This sidebar setting is a teaching convenience, not authentication. '
        "All tools are read-only; no tickets or leave records can be changed.</div>",
        unsafe_allow_html=True,
    )


def _render_live_graph(
    graph_slot: Any,
    note_slot: Any,
    active_node: str | None,
    completed_nodes: set[str],
    note: str,
) -> None:
    """Render observable LangGraph node status without exposing model chain-of-thought."""
    nodes = {
        "START": ("START", "circle"),
        "assistant": ("Assistant model", "box"),
        "tools": ("Read-only tools", "box"),
        "step_limit": ("Step limit", "box"),
        "END": ("END", "circle"),
    }
    dot = [
        "digraph AgentWorkflow {",
        '  graph [rankdir=LR, bgcolor="white", pad="0.28", nodesep="0.55", ranksep="0.8", '
        'fontname="Helvetica", splines=true];',
        '  node [style="filled,rounded", fontname="Helvetica", fontsize=13, margin="0.2,0.12", '
        'color="#94a3b8", fillcolor="#f1f5f9", fontcolor="#334155", penwidth=1.6];',
        '  edge [fontname="Helvetica", fontsize=10, color="#64748b", fontcolor="#475569", arrowsize=0.8];',
    ]
    for node, (label, shape) in nodes.items():
        if node == active_node:
            fill, border, text = "#fff4d6", "#b45309", "#713f12"
            penwidth = 3
        elif node in completed_nodes:
            fill, border, text = "#dcfce7", "#15803d", "#14532d"
            penwidth = 2
        else:
            fill, border, text = "#f1f5f9", "#94a3b8", "#334155"
            penwidth = 1.5
        dot.append(
            f'  {node} [label="{label}", shape="{shape}", fillcolor="{fill}", '
            f'color="{border}", fontcolor="{text}", penwidth={penwidth}];'
        )
    dot.extend(
        [
            '  START -> assistant [label="request"];',
            '  assistant -> tools [label="tool call"];',
            '  tools -> assistant [label="observation"];',
            '  assistant -> END [label="answer"];',
            '  assistant -> step_limit [label="limit reached"];',
            '  step_limit -> END [label="stop"];',
            "  { rank=same; tools; step_limit; }",
            "}",
        ]
    )
    graph_slot.empty()
    with graph_slot:
        st.graphviz_chart("\n".join(dot), use_container_width=True)
    note_slot.caption(note)


def main() -> None:
    defaults = get_settings()

    with st.sidebar:
        st.markdown("## ✦ Agent controls")
        st.caption("Workshop configuration · changes apply to new turns")
        employee_id = st.text_input("Demo employee ID", value=defaults.employee_id).strip().upper()
        model_name = st.text_input("Chat model", value=defaults.model_name).strip()
        database_path = st.text_input("SQLite database", value=str(defaults.database_path)).strip()
        max_model_steps = st.slider("Maximum model calls per turn", min_value=1, max_value=12, value=defaults.max_model_steps)
        st.divider()
        st.markdown("**Data tools**\n\n- Ticket status\n- My tickets\n- Leave balance")
        if st.button("Clear conversation", use_container_width=True):
            st.session_state["agent_messages"] = []
            st.session_state["conversation"] = []
            st.rerun()

    settings_signature = (employee_id, model_name, database_path, max_model_steps)
    previous_signature = st.session_state.get("settings_signature")
    if previous_signature is not None and previous_signature != settings_signature:
        st.session_state["agent_messages"] = []
        st.session_state["conversation"] = []
    st.session_state["settings_signature"] = settings_signature
    st.session_state.setdefault("agent_messages", [])
    st.session_state.setdefault("conversation", [])

    st.markdown(
        '<div class="hero"><div class="hero-kicker">Acme Corp · Session 1</div>'
        '<div class="hero-title">Helpdesk, with the agent in the loop.</div>'
        '<p class="hero-copy">Ask a question, then inspect exactly which tools the agent called and what came back.</p></div>',
        unsafe_allow_html=True,
    )
    metric_columns = st.columns(3)
    metric_columns[0].metric("Orchestration", "LangGraph")
    metric_columns[1].metric("Connected tools", "3 · read-only")
    metric_columns[2].metric("Conversation memory", "This session only")

    chat_tab, learn_tab = st.tabs(["💬  Helpdesk chat", "🧭  How the agent works"])
    with learn_tab:
        _render_explainer(employee_id or "(unset)", model_name or defaults.model_name, max_model_steps)

    with chat_tab:
        st.caption("Try: “What’s the status of INC-1042?”, “List my tickets”, or “How many leave days do I have?”")
        for turn in st.session_state["conversation"]:
            with st.chat_message("user"):
                st.markdown(turn["prompt"])
            with st.chat_message("assistant"):
                st.markdown(turn["answer"])
                with st.expander("Agent graph · executed route", expanded=True):
                    graph_slot = st.empty()
                    graph_note = st.empty()
                    _render_live_graph(
                        graph_slot,
                        graph_note,
                        None,
                        set(turn.get("graph_completed", {"START", "assistant", "END"})),
                        turn.get("graph_note", "Completed graph path for this request."),
                    )
                with st.expander("Turn trace · inspect the agent's work"):
                    _render_trace(turn["trace"])

        prompt = st.chat_input("Ask about a ticket, your tickets, or leave balance…")
        if prompt:
            with st.chat_message("user"):
                st.markdown(prompt)

            trace: list[dict[str, Any]] = []
            try:
                if not employee_id:
                    raise ValueError("Set a demo employee ID in the sidebar before asking a question.")
                if not model_name:
                    raise ValueError("Set a chat model in the sidebar.")
                if not Path(database_path).is_file():
                    raise FileNotFoundError(f"SQLite database not found: {database_path}")
                if not os.getenv("OPENAI_API_KEY"):
                    raise ValueError("OPENAI_API_KEY is not set. Add it to the repository's .env file, then restart the app.")

                agent = _build_runtime(database_path, employee_id, model_name, max_model_steps)
                with st.chat_message("assistant"):
                    st.markdown("#### Live agent execution")
                    graph_slot = st.empty()
                    graph_note = st.empty()
                    graph_state = {"active": "assistant", "completed": {"START"}}

                    def update_graph(active_node: str | None, completed_nodes: set[str], note: str) -> None:
                        graph_state["active"] = active_node
                        graph_state["completed"] = set(completed_nodes) | {"START"}
                        _render_live_graph(
                            graph_slot,
                            graph_note,
                            graph_state["active"],
                            graph_state["completed"],
                            note,
                        )

                    update_graph("assistant", graph_state["completed"], "Starting the assistant node…")
                    with st.status("Running the helpdesk workflow…", expanded=True) as status:
                        status.write("The assistant is evaluating the request and available tools.")
                        answer, trace, turn_messages = _trace_turn(
                            agent,
                            st.session_state["agent_messages"],
                            prompt,
                            on_graph_event=update_graph,
                        )
                        if any(event["kind"] == "tool_result" for event in trace):
                            status.write("A read-only helpdesk tool returned an observation.")
                        status.update(label="Request complete", state="complete", expanded=False)
                    st.markdown(answer)
                    with st.expander("Turn trace · inspect the agent's work", expanded=True):
                        _render_trace(trace)

                st.session_state["agent_messages"].extend([HumanMessage(content=prompt), *turn_messages])
                st.session_state["conversation"].append(
                    {
                        "prompt": prompt,
                        "answer": answer,
                        "trace": trace,
                        "graph_completed": set(graph_state["completed"]),
                        "graph_note": "Completed route highlighted in green.",
                    }
                )
            except Exception as exc:
                message = f"**{type(exc).__name__}:** {exc}"
                with st.chat_message("assistant"):
                    st.error(message)
                    with st.expander("Turn trace · inspect the agent's work"):
                        _render_trace(trace)
                st.session_state["conversation"].append(
                    {"prompt": prompt, "answer": message, "trace": trace}
                )


if __name__ == "__main__":
    main()