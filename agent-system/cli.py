"""Interactive CLI for the Session 1 helpdesk agent."""

from __future__ import annotations

import argparse
import json
import os
import shlex
from typing import Sequence

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from mcp.types import Prompt, PromptArgument
from prompt_toolkit import PromptSession
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from config import Settings, get_settings
from domain import EmployeeProfile, HelpdeskContext
from agents.agent import build_agent
from memory.checkpointer import create_checkpointer
from memory.long_term import LongTermMemory
from memory.store import ConversationStore
from tools.mcp_client import (
    EmployeeProfiles,
    McpPromptError,
    McpSetupError,
    get_helpdesk_prompt,
    list_helpdesk_prompts,
    prompt_label,
)

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


def _print_banner(employee_id: str, profile: EmployeeProfile | None = None) -> None:
    who = f"[bold]{employee_id}[/]" + (f" ({escape(profile.summary())})" if profile else "")
    console.print(
        Panel(
            f"Signed in as demo employee {who}. Ask about your tickets or leave balance, or ask to raise a ticket.\n"
            "Submit with [bold]Enter[/]; use [bold]Shift+Enter[/] to add a line.\n"
            "Use [cyan]/help[/] for commands; [cyan]/exit[/] to quit.",
            title="Acme Helpdesk Agent · Session 2",
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
    commands.add_row("/whoami", "Show the configured demo identity and its profile")
    commands.add_row("/prompts", "List the helpdesk server's prompt templates")
    commands.add_row("/prompt <name> key=value ...", "Run a prompt template as your message")
    commands.add_row("/exit", "End the chat (also: quit, exit)")
    console.print(Panel(commands, title="Chat commands", border_style="cyan"))


def parse_prompt_command(argument: str) -> tuple[str, dict[str, str]]:
    """Split `name key=value ...` (shell-style quoting) into a prompt name and its arguments."""
    try:
        tokens = shlex.split(argument)
    except ValueError as exc:
        raise ValueError(
            f"Could not read the arguments ({exc}). "
            "Wrap values that contain spaces or apostrophes in double quotes."
        ) from exc
    if not tokens or "=" in tokens[0]:
        raise ValueError("Usage: /prompt <name> key=value ... (see /prompts).")
    values: dict[str, str] = {}
    for token in tokens[1:]:
        key, separator, value = token.partition("=")
        if not key or not separator:
            raise ValueError(f"Arguments must look like key=value, not '{token}'.")
        values[key] = value
    return tokens[0], values


def _argument_line(argument: PromptArgument) -> str:
    optional = " (optional)" if not argument.required else ""
    description = f": {argument.description}" if argument.description else ""
    return escape(f"{argument.name}{optional}{description}")


def _print_prompts(prompts: Sequence[Prompt]) -> None:
    table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    table.add_column("Prompt", style="cyan", no_wrap=True)
    table.add_column("Arguments")
    table.add_column("What it does")
    for prompt in prompts:
        arguments = "\n".join(_argument_line(a) for a in prompt.arguments or [])
        table.add_row(escape(prompt.name), arguments or "-", escape(prompt.description or ""))
    console.print(Panel(table, title="Prompt templates", border_style="cyan"))
    console.print("[dim]Run one with /prompt <name> key=value ... (quote values with spaces).[/]")


def _resolve_prompt(settings: Settings, argument: str) -> tuple[str, str]:
    """Check a /prompt command against the server's templates; return its label and text."""
    name, values = parse_prompt_command(argument)
    prompts = {p.name: p for p in list_helpdesk_prompts(settings.mcp_url, settings.mcp_secret)}
    prompt = prompts.get(name)
    if prompt is None:
        raise ValueError(f"Unknown prompt '{name}'. Available: {', '.join(prompts) or 'none'}.")
    accepted = {a.name for a in prompt.arguments or []}
    if unknown := sorted(values.keys() - accepted):
        raise ValueError(
            f"'{name}' has no argument {', '.join(unknown)}. "
            f"Accepted: {', '.join(sorted(accepted)) or 'none'}."
        )
    required = {a.name for a in prompt.arguments or [] if a.required}
    if missing := sorted(required - values.keys()):
        raise ValueError(f"'{name}' needs {', '.join(missing)}. See /prompts.")
    text = get_helpdesk_prompt(settings.mcp_url, settings.mcp_secret, name, values)
    return prompt_label(prompt, values), text


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


def _stream_turn(
    app, payload: object, thread_id: str, employee_id: str
) -> tuple[str, list[str]]:
    """Run or resume the agent, printing tool activity; returns the final text and tool names."""
    response_text = ""
    tool_names: list[str] = []
    with console.status("Thinking…", spinner="dots", spinner_style="cyan"):
        for event in app.stream(
            payload,
            {"configurable": {"thread_id": thread_id}},
            context=HelpdeskContext(employee_id=employee_id),
            stream_mode="updates",
            version="v2",
        ):
            if event.get("type") != "updates":
                continue
            for node_update in event["data"].values():
                if not isinstance(node_update, dict):
                    continue
                for message in node_update.get("messages", []):
                    if isinstance(message, AIMessage) and message.tool_calls:
                        for tool_call in message.tool_calls:
                            tool_names.append(tool_call["name"])
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
    return response_text, tool_names


def _pending_action(app, thread_id: str) -> dict | None:
    state = app.get_state({"configurable": {"thread_id": thread_id}})
    for interrupt in state.interrupts:
        requests = interrupt.value.get("action_requests", [])
        if requests:
            return dict(requests[0])
    return None


def _ask_decision(pending: dict) -> Command:
    """Prompt for approve/edit/reject; the write cannot run without this answer."""
    args = dict(pending["args"])
    console.print(
        Panel(
            Syntax(json.dumps(args, ensure_ascii=False, indent=2), "json", theme="ansi_dark"),
            title=f"Approval required · {pending['name']}",
            border_style="magenta",
        )
    )
    while True:
        choice = input("[a]pprove, [e]dit, [r]eject › ").strip().casefold()
        if choice in {"a", "approve"}:
            decision: dict = {"type": "approve"}
        elif choice in {"r", "reject"}:
            decision = {"type": "reject", "message": "The user rejected this action."}
        elif choice in {"e", "edit"}:
            for field in args:
                value = input(f"{field} [{args[field]}] › ").strip()
                if value:
                    args[field] = value
            decision = {
                "type": "edit",
                "edited_action": {"name": pending["name"], "args": args},
            }
        else:
            continue
        return Command(resume={"decisions": [decision]})


def run_chat(employee_id: str | None = None) -> None:
    settings = get_settings()
    if employee_id:
        from dataclasses import replace

        settings = replace(settings, employee_id=employee_id.strip().upper())
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[red]OPENAI_API_KEY is not set. Add it to .env before starting the chat.[/]")
        return

    try:
        app = build_agent(
            settings,
            checkpointer=create_checkpointer(settings.memory_database_path),
            long_term_memory=LongTermMemory(settings.memory_database_path),
        )
    except McpSetupError as exc:
        console.print(f"[red]{escape(str(exc))}[/]")
        return
    store = ConversationStore(settings.memory_database_path)
    thread_id = store.create_conversation(settings.employee_id)
    profiles = EmployeeProfiles(settings.mcp_url, settings.mcp_secret)
    prompt_session: PromptSession[str] = PromptSession(
        multiline=True,
        history=InMemoryHistory(),
        key_bindings=_create_input_bindings(),
        prompt_continuation="    · ",
    )
    _print_banner(settings.employee_id, profiles.get(settings.employee_id))

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

        model_text = text
        command = parse_command(text)
        if command and command[0] == "prompt":
            try:
                text, model_text = _resolve_prompt(settings, command[1])
            except (ValueError, McpPromptError) as exc:
                console.print(f"[red]{escape(str(exc))}[/]")
                continue
            console.print(Panel(Text(model_text), title="Prompt template", border_style="dim"))
        elif command:
            name, _ = command
            if name in {"exit", "quit"}:
                console.print("[dim]Goodbye.[/]")
                break
            if name == "help":
                _print_help()
            elif name == "prompts":
                try:
                    _print_prompts(list_helpdesk_prompts(settings.mcp_url, settings.mcp_secret))
                except McpPromptError as exc:
                    console.print(f"[red]{escape(str(exc))}[/]")
            elif name == "clear":
                console.clear()
                _print_banner(settings.employee_id, profiles.get(settings.employee_id))
            elif name == "reset":
                thread_id = store.create_conversation(settings.employee_id)
                console.print(Panel("Started a new conversation.", border_style="yellow"))
            elif name == "whoami":
                console.print(f"Configured demo identity: [bold cyan]{settings.employee_id}[/]")
                if profile := profiles.get(settings.employee_id):
                    console.print(escape(profile.summary()))
                    if profile.manager_name:
                        console.print(f"Manager: {escape(profile.manager_name)}")
            else:
                console.print(
                    f"[yellow]Unknown command:[/] /{name}. Use [cyan]/help[/] to see available commands."
                )
            continue

        response_text = ""
        tool_names: list[str] = []
        try:
            payload: object = {"messages": [HumanMessage(content=model_text)]}
            while True:
                turn_text, turn_tools = _stream_turn(app, payload, thread_id, settings.employee_id)
                response_text = turn_text or response_text
                tool_names += turn_tools
                pending = _pending_action(app, thread_id)
                if pending is None:
                    break
                payload = _ask_decision(pending)
            if not response_text:
                response_text = "I couldn't complete that request. Please try again."
            store.add_message(thread_id, settings.employee_id, "user", text)
            store.add_message(
                thread_id, settings.employee_id, "assistant", response_text, tool_names=tool_names
            )
            console.print(
                Panel(Markdown(response_text), title="Helpdesk Agent", border_style="green", padding=(1, 2))
            )
        except Exception as exc:  # keep the workshop loop alive after provider failures
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
    args = parser.parse_args(argv)
    run_chat(args.employee_id)


if __name__ == "__main__":
    main()
