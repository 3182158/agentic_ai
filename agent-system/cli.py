"""Interactive CLI for the Session 1 helpdesk agent."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console
from rich.panel import Panel

from config import get_settings
from data.repository import HelpdeskRepository
from graph.agent import build_agent

console = Console()


def run_chat(employee_id: str | None = None, database_path=None) -> None:
    settings = get_settings()
    if employee_id:
        from dataclasses import replace

        settings = replace(settings, employee_id=employee_id.strip().upper())
    if database_path:
        from dataclasses import replace

        settings = replace(settings, database_path=database_path)
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[red]OPENAI_API_KEY is not set. Add it to .env before starting the chat.[/]")
        return

    repository = HelpdeskRepository(settings.database_path)
    app = build_agent(settings, repository)
    history: list[HumanMessage | AIMessage | ToolMessage] = []
    console.print(
        Panel(
            f"Signed in as demo employee [bold]{settings.employee_id}[/]. "
            "Ask about your tickets or leave balance; type [bold]exit[/] to quit.",
            title="Acme Helpdesk Agent · Session 1",
            border_style="cyan",
        )
    )

    while True:
        try:
            text = console.input("[bold cyan]You › [/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break
        if not text:
            continue
        if text.casefold() in {"exit", "quit"}:
            console.print("[dim]Goodbye.[/]")
            break

        history.append(HumanMessage(content=text))
        response_text = ""
        turn_messages = []
        try:
            for update in app.stream(
                {"messages": history, "model_steps": 0}, stream_mode="updates"
            ):
                for node_name, node_update in update.items():
                    for message in node_update.get("messages", []):
                        turn_messages.append(message)
                        if isinstance(message, AIMessage) and message.tool_calls:
                            for tool_call in message.tool_calls:
                                console.print(
                                    f"[yellow]Tool request[/] [bold]{tool_call['name']}[/]: "
                                    f"{json.dumps(tool_call['args'], ensure_ascii=False)}"
                                )
                        elif isinstance(message, ToolMessage):
                            console.print(
                                f"[green]Tool result[/] [bold]{message.name}[/]: "
                                f"{message.content}"
                            )
                        elif isinstance(message, AIMessage):
                            response_text = str(message.content)
            history.extend(turn_messages)
            if not response_text:
                response_text = "I couldn't complete that request. Please try again."
            console.print(f"[bold green]Agent ›[/] {response_text}\n")
        except Exception as exc:  # keep the workshop loop alive after provider failures
            history.pop()
            console.print(f"[red]Request failed: {type(exc).__name__}: {exc}[/]\n")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--employee-id", help="demo identity supplied by the application (default E104)")
    parser.add_argument("--database", type=str, help="path to the SQLite helpdesk database")
    args = parser.parse_args(argv)
    run_chat(args.employee_id, args.database)


if __name__ == "__main__":
    main()
