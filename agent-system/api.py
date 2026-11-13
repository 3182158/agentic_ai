"""FastAPI server exposing the helpdesk agent over HTTP.

The employee identity is the trusted demo identity from configuration unless the caller passes
`employee_id`; this is a workshop setting, not authentication.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agents.agent import build_agent
from config import get_settings
from memory.checkpointer import create_checkpointer
from memory.long_term import LongTermMemory
from memory.service import ChatService
from memory.store import ConversationStore


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str | None = None
    employee_id: str | None = None


class Decision(BaseModel):
    interrupt_id: str
    action_index: int
    decision: Literal["approve", "edit", "reject"]
    edited_args: dict[str, Any] | None = None
    reason: str = ""


class DecisionsRequest(BaseModel):
    decisions: list[Decision]
    employee_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    tool_names: list[str]
    pending_approval: bool
    pending_actions: list[dict[str, Any]] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = ConversationStore(settings.memory_database_path)
    # build_agent loads MCP tools with asyncio.run, which needs a thread without a running loop.
    agent = await asyncio.to_thread(
        build_agent,
        settings,
        checkpointer=create_checkpointer(settings.memory_database_path),
        long_term_memory=LongTermMemory(settings.memory_database_path),
    )
    app.state.settings = settings
    app.state.service = ChatService(agent, store)
    yield


app = FastAPI(title="Helpdesk Agent API", version="0.1.0", lifespan=lifespan)


def _user(employee_id: str | None) -> str:
    return (employee_id or app.state.settings.employee_id).strip().upper()


def _respond(thread_id: str, user_id: str, result: dict[str, Any]) -> ChatResponse:
    service: ChatService = app.state.service
    pending = service.pending_approvals(thread_id, user_id) if result["pending_approval"] else []
    return ChatResponse(
        thread_id=thread_id,
        answer=result["answer"],
        tool_names=result["tool_names"],
        pending_approval=result["pending_approval"],
        pending_actions=pending,
    )


def _guard(exc: Exception) -> HTTPException:
    if isinstance(exc, (KeyError, LookupError)):
        return HTTPException(404, "Conversation not found.")
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    return HTTPException(502, f"{type(exc).__name__}: {exc}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    service: ChatService = app.state.service
    user_id = _user(request.employee_id)
    try:
        thread_id = request.thread_id or service.start_conversation(user_id)
        result = service.send(thread_id, user_id, request.message)
        return _respond(thread_id, user_id, result)
    except Exception as exc:
        raise _guard(exc) from exc


@app.get("/chat/{thread_id}/approvals")
def approvals(thread_id: str, employee_id: str | None = None) -> list[dict[str, Any]]:
    try:
        return app.state.service.pending_approvals(thread_id, _user(employee_id))
    except Exception as exc:
        raise _guard(exc) from exc


@app.post("/chat/{thread_id}/decisions", response_model=ChatResponse)
def decisions(thread_id: str, request: DecisionsRequest) -> ChatResponse:
    user_id = _user(request.employee_id)
    payload = [d.model_dump(exclude_none=True) for d in request.decisions]
    try:
        result = app.state.service.resume_approvals(thread_id, user_id, payload)
        return _respond(thread_id, user_id, result)
    except Exception as exc:
        raise _guard(exc) from exc


@app.get("/chat/{thread_id}/messages")
def messages(thread_id: str, employee_id: str | None = None) -> list[dict[str, Any]]:
    try:
        return app.state.service.store.get_messages(thread_id, _user(employee_id))
    except Exception as exc:
        raise _guard(exc) from exc


@app.get("/conversations")
def conversations(employee_id: str | None = None) -> list[dict[str, Any]]:
    return app.state.service.store.list_conversations(_user(employee_id))
