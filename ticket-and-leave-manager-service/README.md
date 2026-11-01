# Ticket and Leave Manager MCP service

MCP server (streamable HTTP) exposing `get_ticket_status`, `list_my_tickets`, `check_leave_balance`, `create_ticket`, `get_leave_history` and `apply_leave`.

## Run

```bash
cd ticket-and-leave-manager-service
uv sync
uv run python -m ticket_leave_mcp        # http://127.0.0.1:9000/mcp
```

The secret is read from `HELPDESK_MCP_SECRET` in the repo-root `.env`. An exported shell variable of the same name overrides `.env`, so don't export a different value.

## Connect the agent

Put the secret in the repo-root `.env`, along with the server URL:

```
HELPDESK_MCP_URL=http://127.0.0.1:9000/mcp
HELPDESK_MCP_SECRET=<at least 32 random characters>
```

When `HELPDESK_MCP_URL` is set, the agent calls this server. Otherwise it reads the SQLite database directly.

## Create a token for manual testing

```bash
uv run python scripts/make_token.py E104              # valid for 1 hour
uv run python scripts/make_token.py E104 --ttl 86400  # valid for 1 day
```

Send it as `Authorization: Bearer <token>`. A 401 means the token was signed with a different secret than the running server uses; restart the server after changing the secret.

## Security model

- The agent signs a 60-second HS256 token whose `sub` is the signed-in employee. The server takes the identity only from that token; no tool accepts an employee ID.
- Write tools require an `Idempotency-Key` header (`<tool>:<tool_call_id>`), so a retried approval cannot double-create.
- Human approval stays in the agent; the server only receives approved writes.

## Tests

```bash
uv run pytest
```
