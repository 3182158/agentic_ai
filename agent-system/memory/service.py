"""Runs one chat turn: agent state goes to the checkpointer, display text to the store."""

from __future__ import annotations

import json
from typing import Any, NotRequired, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from domain import HelpdeskContext
from memory.store import ConversationStore

FALLBACK_ANSWER = "I couldn't complete that request. Please try again."
AWAITING_APPROVAL = "Please review the pending actions below. Nothing will be submitted without your approval."


class ApprovalDecision(TypedDict):
    interrupt_id: str
    action_index: int
    decision: str
    edited_args: NotRequired[dict[str, Any]]
    reason: NotRequired[str]


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
        """Return the first draft for single-action callers; the UI uses pending_approvals."""
        pending = self.pending_approvals(thread_id, user_id)
        if not pending:
            return None
        return {
            key: value for key, value in pending[0].items()
            if key not in {"interrupt_id", "action_index"}
        }

    def pending_approvals(self, thread_id: str, user_id: str) -> list[dict[str, Any]]:
        """Read every paused action, preserving its interrupt id and position."""
        self.store.get_conversation(thread_id, user_id)
        state = self.agent.get_state({"configurable": {"thread_id": thread_id}})
        return [
            {**request, "interrupt_id": interrupt.id, "action_index": index}
            for interrupt in state.interrupts
            for index, request in enumerate(interrupt.value.get("action_requests", []))
        ]

    def resume(
        self,
        thread_id: str,
        user_id: str,
        decision: str,
        edited_args: dict[str, Any] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Compatibility entry point for a single pending action only."""
        pending = self.pending_approvals(thread_id, user_id)
        if not pending:
            raise ValueError("There is no pending approval for this conversation.")
        if len(pending) != 1:
            raise ValueError("Provide a separate decision for every pending action.")
        return self.resume_approvals(thread_id, user_id, [{
            "interrupt_id": pending[0]["interrupt_id"],
            "action_index": pending[0]["action_index"],
            "decision": decision,
            "edited_args": edited_args if edited_args is not None else {},
            "reason": reason,
        }])

    def resume_approvals(
        self, thread_id: str, user_id: str, decisions: list[ApprovalDecision]
    ) -> dict[str, Any]:
        """Validate all decisions, then resume each interrupt in its original action order."""
        pending = self.pending_approvals(thread_id, user_id)
        if not pending:
            raise ValueError("There is no pending approval for this conversation.")
        by_action = {
            (decision["interrupt_id"], decision["action_index"]): decision
            for decision in decisions
        }
        expected = {(action["interrupt_id"], action["action_index"]) for action in pending}
        if len(by_action) != len(decisions) or set(by_action) != expected:
            raise ValueError(
                "Provide exactly one decision for every pending action; approvals may have changed."
            )
        resume_map: dict[str, Any] = {}
        for action in pending:
            response = by_action[(action["interrupt_id"], action["action_index"])]
            decision = response["decision"]
            if decision == "approve":
                payload: dict[str, Any] = {"type": "approve"}
            elif decision == "edit":
                if "edited_args" not in response:
                    raise ValueError("Edited arguments are required for an edit decision.")
                payload = {
                    "type": "edit",
                    "edited_action": {"name": action["name"], "args": response["edited_args"]},
                }
            elif decision == "reject":
                payload = {
                    "type": "reject",
                    "message": response.get("reason") or "The user rejected this action.",
                }
            else:
                raise ValueError(f"Unknown decision: {decision}")
            interrupt_response = resume_map.setdefault(action["interrupt_id"], {"decisions": []})
            interrupt_response["decisions"].append(payload)
        result = self.agent.invoke(
            Command(resume=resume_map),
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
