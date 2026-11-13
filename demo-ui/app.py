"""Thin Streamlit demo UI that talks only to the helpdesk agent's FastAPI backend."""

from __future__ import annotations

import json
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 180

EMPLOYEES = {
    "E100": "Jordan Lee · Finance",
    "E101": "Ravi Shah · Manager",
    "E102": "Meera Patel · IT admin",
    "E103": "Dev Morgan · HR manager",
    "E104": "Asha Raman · Engineering",
    "E105": "Luis Gomez · Sales",
    "E106": "Hana Kim · Marketing",
    "E107": "Priya Nair · Finance",
    "E108": "Noah Brooks · IT Operations",
    "E109": "Imani Okafor · Support",
}

st.set_page_config(page_title="Helpdesk Agent Demo", page_icon="🛟", layout="wide")


def api(method: str, path: str, **kwargs):
    response = requests.request(method, f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"{response.status_code}: {detail}")
    return response.json()


def reset_conversation() -> None:
    st.session_state.update(thread_id=None, messages=[], pending=[])


def load_conversation(thread_id: str, employee: str) -> None:
    rows = api("GET", f"/chat/{thread_id}/messages", params={"employee_id": employee})
    pending = api("GET", f"/chat/{thread_id}/approvals", params={"employee_id": employee})
    st.session_state.update(
        thread_id=thread_id,
        messages=[{"role": r["role"], "content": r["content"], "tools": r["tool_names"]} for r in rows],
        pending=pending,
    )


def apply_result(result: dict) -> None:
    st.session_state.thread_id = result["thread_id"]
    st.session_state.messages.append(
        {"role": "assistant", "content": result["answer"], "tools": result["tool_names"]}
    )
    st.session_state.pending = result["pending_actions"]


for key, default in (("thread_id", None), ("messages", []), ("pending", []), ("employee", "E104")):
    st.session_state.setdefault(key, default)

with st.sidebar:
    st.title("🛟 Helpdesk Agent")
    employee = st.selectbox(
        "Demo employee",
        list(EMPLOYEES),
        format_func=lambda e: f"{e} — {EMPLOYEES[e]}",
        index=list(EMPLOYEES).index(st.session_state.employee),
    )
    if employee != st.session_state.employee:
        st.session_state.employee = employee
        reset_conversation()
        st.rerun()
    st.caption("Workshop identity selector, not authentication.")
    st.caption(f"Backend: `{API_URL}`")
    try:
        api("GET", "/health")
        st.success("API online")
    except Exception as exc:
        st.error(f"API unreachable: {exc}")

    if st.button("➕ New chat", use_container_width=True):
        reset_conversation()
        st.rerun()
    st.subheader("History")
    try:
        for convo in api("GET", "/conversations", params={"employee_id": employee})[:15]:
            label = convo["title"] or "Conversation"
            if st.button(label, key=convo["thread_id"], use_container_width=True):
                load_conversation(convo["thread_id"], employee)
                st.rerun()
    except Exception:
        st.caption("History unavailable.")

st.header("Chat with the helpdesk agent")
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("tools"):
            st.caption("Tools used: " + ", ".join(message["tools"]))

if st.session_state.pending:
    st.warning("Review the pending actions. Nothing runs until every action has a decision.")
    decisions = []
    complete = True
    for action in st.session_state.pending:
        key = f"{action['interrupt_id']}:{action['action_index']}"
        with st.container(border=True):
            st.markdown(f"**{action['name']}**")
            args_text = st.text_area(
                "Arguments (editable JSON)",
                json.dumps(action["args"], indent=2, ensure_ascii=False),
                key=f"args:{key}",
            )
            choice = st.radio("Decision", ["Approve", "Reject"], index=None, horizontal=True, key=f"d:{key}")
        if choice is None:
            complete = False
            continue
        entry = {
            "interrupt_id": action["interrupt_id"],
            "action_index": action["action_index"],
            "decision": choice.lower(),
        }
        if choice == "Approve":
            try:
                args = json.loads(args_text)
            except ValueError:
                st.error("Arguments must be valid JSON.")
                complete = False
                continue
            if args != action["args"]:
                entry.update(decision="edit", edited_args=args)
        decisions.append(entry)
    if st.button("Submit decisions", type="primary", disabled=not complete):
        try:
            with st.spinner("Applying decisions…"):
                result = api(
                    "POST",
                    f"/chat/{st.session_state.thread_id}/decisions",
                    json={"decisions": decisions, "employee_id": employee},
                )
            apply_result(result)
        except Exception as exc:
            st.error(str(exc))
        st.rerun()

prompt = st.chat_input("Ask about tickets or leave…", disabled=bool(st.session_state.pending))
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    try:
        with st.spinner("Thinking…"):
            result = api(
                "POST",
                "/chat",
                json={"message": prompt, "thread_id": st.session_state.thread_id, "employee_id": employee},
            )
        apply_result(result)
    except Exception as exc:
        st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {exc}", "tools": []})
    st.rerun()
