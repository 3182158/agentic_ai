"""Interactive CLI for the Session 1 helpdesk agent."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from prompt_toolkit import PromptSession
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from config import get_settings
from data.repository import HelpdeskRepository
from graph.agent import build_agent

console = Console()

# prompt_toolkit normally maps this common xterm Shift+Enter sequence to Enter.
# Keep it distinct so Enter can submit while Shift+Enter remains a newline.
ANSI_SEQUENCES["\x1b[27;2;13~"] = Keys.ControlJ
ANSI_SEQUENCES["\x1b[13;2u"] = Keys.ControlJ
ANSI_SEQUENCES["\x0a"] = Keys.ControlM


def _create_input_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add(Keys.ControlM)
    def _submit(event) -> None:
        event.current_buffer.validate_and_handle()

    @bindings.add(Keys.ControlJ)
    def _insert_newline(event) -> None:
        event.current_buffer.newline(copy_margin=True)

    return bindings


def parse_command(text: str) -> tuple[str, str] | None:
    """Return a slash command and its optional argument, if present."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped[1:].split(maxsplit=1)
    command = parts[0].casefold() if parts else ""
    argument = parts[1].strip() if len(parts) > 1 else ""
    return command, argument


def _content_as_text(content: object) -> str:
    """Convert common LangChain text and content-block responses to readable text."""
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


def _print_banner(employee_id: str) -> None:
    console.print(
        Panel(
            f"Signed in as demo employee [bold]{employee_id}[/]. Ask about your tickets or leave balance.\n"
            "Submit with [bold]Enter[/]; use [bold]Shift+Enter[/] to add a line.\n"
            "Use [cyan]/help[/] for commands; [cyan]/exit[/] to quit.",
            title="Acme Helpdesk Agent · Session 1",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def _print_help() -> None:
    commands = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    commands.add_column("Command", style="cyan", no_wrap=True)
    commands.add_column("What it does")
    commands.add_row("/help", "Show this command list")
    commands.add_row("/clear", "Clear the terminal screen")
    commands.add_row("/reset", "Forget conversation context and start fresh")
    commands.add_row("/whoami", "Show the configured demo identity")
    commands.add_row("/exit", "End the chat (also: quit, exit)")
    console.print(Panel(commands, title="Chat commands", border_style="cyan"))


def _print_tool_message(message: ToolMessage) -> None:
    content = _content_as_text(message.content)
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        body = Markdown(content)
    else:
        body = Syntax(
            json.dumps(parsed, ensure_ascii=False, indent=2, default=str),
            "json",
            theme="ansi_dark",
            word_wrap=True,
        )
    console.print(Panel(body, title=f"Tool result · {message.name or 'tool'}", border_style="green"))


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
    prompt_session: PromptSession[str] = PromptSession(
        multiline=True,
        history=InMemoryHistory(),
        key_bindings=_create_input_bindings(),
        prompt_continuation="    · ",
    )
    _print_banner(settings.employee_id)

    while True:
        try:
            text = prompt_session.prompt("You › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break
        if not text:
            continue
        if text.casefold() in {"exit", "quit"}:
            console.print("[dim]Goodbye.[/]")
            break

        command = parse_command(text)
        if command:
            name, _ = command
            if name in {"exit", "quit"}:
                console.print("[dim]Goodbye.[/]")
                break
            if name == "help":
                _print_help()
            elif name == "clear":
                console.clear()
                _print_banner(settings.employee_id)
            elif name == "reset":
                history.clear()
                console.print(Panel("Conversation context cleared.", border_style="yellow"))
            elif name == "whoami":
                console.print(f"Configured demo identity: [bold cyan]{settings.employee_id}[/]")
            else:
                console.print(
                    f"[yellow]Unknown command:[/] /{name}. Use [cyan]/help[/] to see available commands."
                )
            continue

        history.append(HumanMessage(content=text))
        response_text = ""
        turn_messages = []
        try:
            with console.status("Thinking…", spinner="dots", spinner_style="cyan"):
                for update in app.stream(
                    {"messages": history, "model_steps": 0}, stream_mode="updates"
                ):
                    for node_update in update.values():
                        for message in node_update.get("messages", []):
                            turn_messages.append(message)
                            if isinstance(message, AIMessage) and message.tool_calls:
                                for tool_call in message.tool_calls:
                                    args = json.dumps(
                                        tool_call["args"], ensure_ascii=False, indent=2, default=str
                                    )
                                    console.print(
                                        Panel(
                                            Syntax(args, "json", theme="ansi_dark", word_wrap=True),
                                            title=f"Tool request · {tool_call['name']}",
                                            border_style="yellow",
                                        )
                                    )
                            elif isinstance(message, ToolMessage):
                                _print_tool_message(message)
                            elif isinstance(message, AIMessage):
                                response_text = _content_as_text(message.content)
            history.extend(turn_messages)
            if not response_text:
                response_text = "I couldn't complete that request. Please try again."
            console.print(
                Panel(Markdown(response_text), title="Helpdesk Agent", border_style="green", padding=(1, 2))
            )
        except Exception as exc:  # keep the workshop loop alive after provider failures
            history.pop()
            console.print(
                Panel(
                    f"{type(exc).__name__}: {exc}",
                    title="Request failed",
                    border_style="red",
                )
            )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--employee-id", help="demo identity supplied by the application (default E104)"
    )
    parser.add_argument("--database", type=str, help="path to the SQLite helpdesk database")
    args = parser.parse_args(argv)
    run_chat(args.employee_id, args.database)


if __name__ == "__main__":
    main()
