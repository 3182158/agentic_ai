"""Runs one chat turn: agent state goes to the checkpointer, display text to the store."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from domain import HelpdeskContext
from memory.store import ConversationStore

FALLBACK_ANSWER = "I couldn't complete that request. Please try again."
AWAITING_APPROVAL = "I've drafted this action and need your approval before it runs."


def content_as_text(content: Any) -> str:
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


class ChatService:
    def __init__(self, agent: Any, store: ConversationStore) -> None:
        self.agent = agent
        self.store = store

    def start_conversation(self, user_id: str) -> str:
        return self.store.create_conversation(user_id)

    def send(
        self, thread_id: str, user_id: str, prompt: str, *, display: str | None = None
    ) -> dict[str, Any]:
        """Run a turn and persist display messages; ownership is checked before any work.

        `prompt` is sent to the model; `display` is what the transcript shows when it differs.
        """
        self.store.get_conversation(thread_id, user_id)
        # The checkpointer restores prior state for this thread, so only the new message is sent.
        result = self.agent.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={"configurable": {"thread_id": thread_id}},
            context=HelpdeskContext(employee_id=user_id),
        )
        self.store.add_message(thread_id, user_id, "user", display or prompt)
        return self._finish(thread_id, user_id, result)

    def pending_approval(self, thread_id: str, user_id: str) -> dict[str, Any] | None:
        """Return the paused write action awaiting a decision, read from checkpointed state."""
        self.store.get_conversation(thread_id, user_id)
        state = self.agent.get_state({"configurable": {"thread_id": thread_id}})
        for interrupt in state.interrupts:
            requests = interrupt.value.get("action_requests", [])
            if requests:
                return dict(requests[0])
        return None

    def resume(
        self,
        thread_id: str,
        user_id: str,
        decision: str,
        edited_args: dict[str, Any] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Apply approve/edit/reject to the paused action; the write runs only on approve/edit."""
        pending = self.pending_approval(thread_id, user_id)
        if pending is None:
            raise ValueError("There is no pending approval for this conversation.")
        if decision == "approve":
            payload: dict[str, Any] = {"type": "approve"}
        elif decision == "edit":
            payload = {
                "type": "edit",
                "edited_action": {"name": pending["name"], "args": edited_args or {}},
            }
        elif decision == "reject":
            payload = {"type": "reject", "message": reason or "The user rejected this action."}
        else:
            raise ValueError(f"Unknown decision: {decision}")
        result = self.agent.invoke(
            Command(resume={"decisions": [payload]}),
            config={"configurable": {"thread_id": thread_id}},
            context=HelpdeskContext(employee_id=user_id),
        )
        return self._finish(thread_id, user_id, result)

    def _finish(self, thread_id: str, user_id: str, result: dict[str, Any]) -> dict[str, Any]:
        messages = list(result["messages"])
        last_human = max(
            (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1
        )
        turn = messages[last_human + 1 :]
        tool_names = [
            call["name"] for m in turn if isinstance(m, AIMessage) for call in m.tool_calls
        ]
        final = turn[-1] if turn else None
        answer = ""
        if result.get("__interrupt__"):
            answer = AWAITING_APPROVAL
        elif isinstance(final, AIMessage) and not final.tool_calls:
            answer = content_as_text(final.content)
        answer = answer or FALLBACK_ANSWER

        message_id = self.store.add_message(
            thread_id, user_id, "assistant", answer, tool_names=tool_names
        )
        return {
            "answer": answer,
            "message_id": message_id,
            "tool_names": tool_names,
            "pending_approval": bool(result.get("__interrupt__")),
        }

    def record_error(self, thread_id: str, user_id: str, prompt: str, error_text: str) -> None:
        """Keep failed turns visible in the transcript without touching agent state."""
        self.store.add_message(thread_id, user_id, "user", prompt)
        self.store.add_message(thread_id, user_id, "assistant", error_text, is_error=True)
