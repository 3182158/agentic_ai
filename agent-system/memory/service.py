"""Runs one chat turn: agent state goes to the checkpointer, display text to the store."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from memory.store import ConversationStore

FALLBACK_ANSWER = "I couldn't complete that request. Please try again."


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

    def send(self, thread_id: str, user_id: str, prompt: str) -> dict[str, Any]:
        """Run a turn and persist display messages; ownership is checked before any work."""
        self.store.get_conversation(thread_id, user_id)
        # The checkpointer restores prior state for this thread, so only the new message is sent.
        result = self.agent.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={"configurable": {"thread_id": thread_id}},
        )
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
        if isinstance(final, AIMessage) and not final.tool_calls:
            answer = content_as_text(final.content)
        answer = answer or FALLBACK_ANSWER

        self.store.add_message(thread_id, user_id, "user", prompt)
        message_id = self.store.add_message(
            thread_id, user_id, "assistant", answer, tool_names=tool_names
        )
        return {"answer": answer, "message_id": message_id, "tool_names": tool_names}

    def record_error(self, thread_id: str, user_id: str, prompt: str, error_text: str) -> None:
        """Keep failed turns visible in the transcript without touching agent state."""
        self.store.add_message(thread_id, user_id, "user", prompt)
        self.store.add_message(thread_id, user_id, "assistant", error_text, is_error=True)
