"""Tools that let the agent save and delete long-term facts for the signed-in employee."""

from __future__ import annotations

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, tool

from domain import HelpdeskContext
from memory.long_term import LongTermMemory


def create_memory_tools(memory: LongTermMemory) -> list[BaseTool]:
    @tool
    def remember_fact(fact: str, runtime: ToolRuntime[HelpdeskContext]) -> str:
        """Save one durable, non-sensitive fact about the employee for future conversations, e.g. their device/OS, work location, or which fix resolved a past issue. Never save passwords, codes, tokens or personal identifiers."""
        return memory.remember(runtime.context.employee_id, fact)

    @tool
    def forget_memory(
        runtime: ToolRuntime[HelpdeskContext], memory_id: int | None = None
    ) -> str:
        """Delete one saved memory by its id, or all saved memories when memory_id is omitted. Use when the employee asks you to forget something."""
        employee_id = runtime.context.employee_id
        if memory_id is None:
            return f"Forgot {memory.forget_all(employee_id)} memories."
        return "Forgotten." if memory.forget(employee_id, memory_id) else "No such memory."

    return [remember_fact, forget_memory]
