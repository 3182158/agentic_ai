# Ticket and Leave Manager MCP service

MCP server (streamable HTTP) exposing `get_ticket_status`, `list_my_tickets`, `check_leave_balance`, `create_ticket`, `get_leave_history` and `apply_leave`. It also offers the signed-in employee's profile as a resource (see [Resources](#resources)) and four sample prompt templates (see [Prompts](#prompts)).

## Run

```bash
cd ticket-and-leave-manager-service
uv sync
uv run python -m ticket_leave_mcp        # http://127.0.0.1:9000/mcp
```

The secret is read from `HELPDESK_MCP_SECRET` in the repo-root `.env`. An exported shell variable of the same name overrides `.env`, so don't export a different value.

## Connect the agent

Put the secret in the repo-root `.env`. Add the URL only if you change the server's host or port (it defaults to the address above):

```
HELPDESK_MCP_SECRET=<at least 32 random characters>
# HELPDESK_MCP_URL=http://127.0.0.1:9000/mcp
```

This server is the agent's only source of helpdesk data. The agent loads its tools straight from here at startup (via `langchain-mcp-adapters`), so start the server first. Tool names, descriptions and schemas live only here: add or change a tool on the server, restart the server and the agent, and the agent can use it with no agent code change.

## Prompts

Besides tools, the server offers sample MCP prompts: templates the user picks that only return text and call nothing themselves. The agent app lists and runs them (see [Prompt templates](../agent-system/README.md#prompt-templates)), and any other MCP client (for example MCP Inspector) can list them with `prompts/list` and render one with `prompts/get`. Like tools, they need a valid bearer token, and none takes an employee ID.

- `raise_it_ticket(issue, category?)` guides drafting a ticket and submitting it with `create_ticket`.
- `request_leave(leave_type, when, reason?)` guides working out exact dates, checking the balance and submitting with `apply_leave`.
- `summarize_my_tickets()` guides summarizing the employee's tickets from `list_my_tickets`.
- `leave_overview()` guides summarizing the leave balance and requests from `check_leave_balance` and `get_leave_history`.

To add or change one, edit `register_prompts` in `src/ticket_leave_mcp/server.py` and restart the server. The agent app discovers prompts like it discovers tools, so it needs no code change: the CLI sees the change on its next `/prompts`, and the Streamlit page after a reload.

## Resources

The server offers one MCP resource: read-only context about the signed-in employee. Unlike a tool, the model does not call it; the application decides when to load it. The agent app reads it as the signed-in employee and adds it to the model's context (see [Employee profile](../agent-system/README.md#employee-profile)), and any other MCP client (for example MCP Inspector) can list it with `resources/list` and read it with `resources/read`. Like tools, it needs a valid bearer token.

- `employee://me/profile` returns JSON with `employee_id`, `full_name`, `department`, `office_location` and `manager_name` (`null` when the employee has no manager). Nothing else is exposed: no email, access role or manager ID.

The employee comes only from the token, so the URI has no employee ID and the server defines no resource template that takes one. A token whose `sub` is not an active employee, such as the agent's `helpdesk-agent` discovery token, can list the resource but gets an error when reading it, so read it with a token signed for the employee.

To add or change one, edit `create_server` in `src/ticket_leave_mcp/server.py` and restart the server. Give the resource function no parameters and reach the request with `mcp.get_context()`: FastMCP registers a resource function that takes any parameter, even `ctx`, as a template, which hides it from `resources/list`.

## Create a token for manual testing

```bash
uv run python scripts/make_token.py E104              # valid for 1 hour
uv run python scripts/make_token.py E104 --ttl 86400  # valid for 1 day
```

Send it as `Authorization: Bearer <token>`. A 401 means the token was signed with a different secret than the running server uses; restart the server after changing the secret.

## Security model

- The agent signs a 60-second HS256 token whose `sub` is the signed-in employee. The server takes the identity only from that token; no tool, prompt or resource accepts an employee ID. Tool discovery at startup uses a token with `sub` `helpdesk-agent`, since listing tools is not an employee action.
- Write tools require an `Idempotency-Key` header (`<tool>:<tool_call_id>`), so a retried approval cannot double-create.
- Human approval stays in the agent; the server only receives approved writes.

## Tests

```bash
uv run pytest
```
