# Session 1: LangGraph Helpdesk Agent

A small, read-only custom agent built on LangGraph. This is the extensible foundation for the later MCP, approvals, specialist routing, RAG, guardrails, and API sessions—not a production service.

## Architecture

```text
CLI ──trusted demo identity──▶ LangGraph assistant ⇄ read-only tools
                                      │                     │
                           short-term message list    SQLite repository
                                                            │
                                                   mock-data/sqlite fixtures
```

- `config.py` loads model, database, demo-identity, and step-limit settings.
- `domain.py` defines typed contracts independent of the model and database.
- `data/repository.py` performs parameterized, read-only SQLite queries.
- `tools/helpdesk.py` exposes typed tools; identity is closed over from application settings, not tool arguments.
- `graph/agent.py` owns the model/tool loop and its maximum model-call count.
- `cli.py` displays tool requests and results and carries recent messages between turns in memory.
- `tests/` tests the repository, identity binding, and graph with a fake model and no API key.

The repository opens SQLite in read-only mode. Employees can look up their own tickets; the fictional `it_admin` role can inspect tickets across owners. Leave and ticket-list tools are always scoped to the configured employee.

## Setup and run

From the repository root:

1. Install the project and test dependencies with `uv sync`.
2. Set `OPENAI_API_KEY` in the ignored `.env` file. Optional settings:
   - `OPENAI_MODEL` (default `gpt-4o-mini`)
   - `HELPDESK_DEMO_EMPLOYEE_ID` (default `E104`, Asha Raman)
   - `HELPDESK_DATABASE_PATH` (default `mock-data/sqlite/acme_helpdesk.sqlite3`)
   - `HELPDESK_MAX_MODEL_STEPS` (default `6`)
3. If the SQLite file is absent, rebuild it from the checked-in SQL fixtures:

   ```bash
   uv run python mock-data/sqlite/build_database.py
   ```

4. Start the conversation:

   ```bash
   uv run python agent-system/cli.py
   ```

Press `Enter` to submit a message; use `Shift+Enter` to add a line to a multi-line message. Prompt history is available while the process is open. Use `/help` to see the built-in commands (`/clear`, `/reset`, `/whoami`, and `/exit`). Tool requests and results are shown in separate, syntax-highlighted panels; agent answers render Markdown. Conversation context, including tool-call messages and observations, lives only in this CLI process and is discarded on exit. There is no checkpointing or durable memory in Session 1.

## Demo prompts

- `What's the status of ticket INC-1042?` — Asha owns this ticket; expect in progress, high priority.
- `And what about its priority?` — follow-up uses the prior conversation context.
- `How many leave days do I have left?` — uses configured employee `E104`, not an ID selected by the model.
- `List my tickets.` — returns only tickets owned by the configured employee.
- `What's the status of ticket INC-9999?` — not found; the agent must not invent a status.
- `What's the weather today?` — politely declined as out of scope.
- For authorization behavior, use another employee's ticket ID; the repository denies access unless the configured demo identity has the `it_admin` role.

Tool-call request arguments and tool observations are printed before the final response so the model-request/application-execution distinction is visible.

## Tests

```bash
uv run pytest agent-system/tests
```

The tests build isolated fixture databases and use a deterministic fake model. They do not require an OpenAI key or network access.

## Evolution boundaries

Session 1 deliberately has no write tools, MCP, human approval, persistent state, specialist agents, RAG, production authentication, or API. Later sessions should preserve the domain contracts and repository/tool seams where useful, while adding each new capability as a separate boundary. `HELPDESK_DEMO_EMPLOYEE_ID` is only a workshop identity selector; it is not authentication, and this CLI must not be exposed as a production security boundary.
