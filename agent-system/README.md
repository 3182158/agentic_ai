# Session 1: LangChain Helpdesk Agent

A small, read-only helpdesk agent built with LangChain's `create_agent` and LangGraph underneath. This is the extensible foundation for later MCP, approvals, specialist routing, RAG, guardrails, and API sessions—not a production service.

## Architecture

```text
CLI ──trusted demo identity──▶ LangChain create_agent ⇄ tools discovered from MCP
                                      │                          │
                           short-term message list     ticket-and-leave MCP service
                                                                 │
                                                        mock-data/sqlite fixtures
```

- `config.py` loads model, MCP connection, demo-identity, and step-limit settings.
- `domain.py` defines typed contracts shared by the agent and its UI.
- `tools/mcp_client.py` loads the helpdesk tools straight from the ticket-and-leave MCP server. Names, descriptions and schemas come from the server; nothing is redefined here, and identity is supplied per call from the runtime context, never by the model.
- `agents/agent.py` builds `create_agent` with model-call and per-tool run limits.
- `cli.py` displays tool requests and results and carries recent messages between turns in memory.
- `tests/` tests tool loading, identity binding, approvals, and the graph against the real MCP service on a local port, using a fake model and no API key.

The agent has no database access of its own: the MCP service owns the data, opens SQLite query-only for reads, and scopes every tool to the signed-in employee. Employees can look up their own tickets; the fictional `it_admin` role can inspect tickets across owners.

## Setup and run

From the repository root:

1. Install the project and test dependencies with `uv sync`.
2. In the ignored `.env` file, set `OPENAI_API_KEY` and `HELPDESK_MCP_SECRET` (it must match the MCP service's secret). Optional settings:
   - `OPENAI_MODEL` (default `gpt-4o-mini`)
   - `HELPDESK_DEMO_EMPLOYEE_ID` (default `E104`, Asha Raman)
   - `HELPDESK_MAX_MODEL_STEPS` (default `6`)
   - `HELPDESK_MCP_URL` (default `http://127.0.0.1:9000/mcp`)
3. Start the [MCP service](../ticket-and-leave-manager-service/README.md); the agent discovers its tools from it at startup. If the service's SQLite file is absent, rebuild it from the checked-in SQL fixtures:

   ```bash
   uv run python mock-data/sqlite/build_database.py
   ```

4. Start the conversation:

   ```bash
   uv run python agent-system/cli.py
   ```

### Streamlit application

Start the browser-based chat and agent walkthrough from the repository root:

```bash
uv run streamlit run agent-system/streamlit_app.py
```

The chat uses the same LangChain agent, MCP tools, and short-term conversation context as the CLI. During a request, **Live agent execution** reflects the built-in model/tools events; expand **Turn trace** under an answer to inspect observable tool requests, arguments, tool results, and the final response. The **How the agent works** tab explains each stage and its trust boundaries. The sidebar lets you change the demo employee, model, chat-memory database path, and per-turn model-call limit; changing the demo identity starts a fresh conversation. This employee selector is only a workshop demo setting—not authentication.

For migration rationale, middleware budgets, streaming behavior, and the multi-agent evolution path, see [the migration guide](../docs/convert-basic-agent-to-create-agent.md).

Press `Enter` to submit a message; use `Shift+Enter` to add a line to a multi-line message. Prompt history is available while the process is open. Use `/help` to see the built-in commands (`/clear`, `/reset`, `/whoami`, and `/exit`). Tool requests and results are shown in separate, syntax-highlighted panels; agent answers render Markdown. Conversation context, including tool-call messages and observations, lives only in this CLI process and is discarded on exit. There is no checkpointing or durable memory in Session 1.

## Demo prompts

- `What's the status of ticket INC-1042?` — Asha owns this ticket; expect in progress, high priority.
- `And what about its priority?` — follow-up uses the prior conversation context.
- `How many leave days do I have left?` — uses configured employee `E104`, not an ID selected by the model.
- `List my tickets.` — returns only tickets owned by the configured employee.
- `What's the status of ticket INC-9999?` — not found; the agent must not invent a status.
- `What's the weather today?` — politely declined as out of scope.
- For authorization behavior, use another employee's ticket ID; the MCP service denies access unless the configured demo identity has the `it_admin` role.

Tool-call request arguments and tool observations are printed before the final response so the model-request/application-execution distinction is visible.

## Later-session demo prompts

### Long-term memory (use two separate conversations)

**Conversation 1:**

1. `I'm on a MacBook and I work remotely from Pune. Please remember that.`
2. `Remember that resetting my MFA token fixed my VPN issue last time.`
3. `My password is Hunter2, remember it.` — the agent should refuse to save passwords or other secrets.

**Conversation 2 (a new thread):**

4. `My VPN is failing again, what should I do?` — use the remembered MacBook, Pune, and MFA-reset facts.
5. `What do you remember about me?`
6. `Forget that I work from Pune.`
7. `Forget everything you know about me.`

### Human-in-the-loop (create_ticket and apply_leave)

- `Raise a high priority ticket: my laptop screen flickers and goes black.` — approve the request; the ticket is created.
- `Create a ticket for printer printing blank pages.` — edit the title or priority, then approve.
- `Raise a ticket for wifi dropping.` — reject the request; the agent should not retry.
- `Apply sick leave for next Monday and Tuesday, I have a fever.`
- `Apply annual leave from 2026-12-24 to 2026-12-31 for vacation.`

## Tests

```bash
uv run pytest agent-system/tests
```

The tests start the MCP service on a local port with an isolated fixture database and use a deterministic fake model. They do not require an OpenAI key or external network access.

## Evolution boundaries

Session 1 deliberately has no write tools, MCP, human approval, persistent state, specialist agents, RAG, production authentication, or API. Later sessions should preserve the domain contracts and repository/tool seams where useful, while adding each new capability as a separate boundary. `HELPDESK_DEMO_EMPLOYEE_ID` is only a workshop identity selector; it is not authentication, and this CLI must not be exposed as a production security boundary.
