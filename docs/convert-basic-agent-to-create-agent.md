# Evolving the Basic LangGraph Agent to `create_agent`

This guide describes a staged conversion of the Session 1 custom `StateGraph` to LangChain's built-in `create_agent`. It keeps the existing domain tools, SQLite repository, identity boundary, Streamlit chat, and tests, while moving the standard model/tool loop into the framework.

> This is an implementation plan, not a code change. Validate the installed LangChain version and middleware behavior before applying it. The project currently depends on `langgraph` and `langchain-openai`; it does not directly declare `langchain`, which provides `create_agent` and its agent middleware.

## Why make the change?

The current implementation in `agent-system/graph/agent.py` is valuable for teaching: it explicitly defines the assistant node, tool node, edges, routing, and model-call cap. `create_agent` is itself built on LangGraph, but supplies a standard agent loop and middleware integration so application code can focus on the model, prompt, tools, and policies.

| Keep the custom `StateGraph` when… | Prefer `create_agent` when… |
|---|---|
| Teaching each graph node and transition is the main goal. | The standard model → tools → model loop is enough. |
| You need custom routing/state transitions beyond the normal tool loop. | You want reusable built-in middleware for limits and other policies. |
| You want direct control of node names and graph construction. | You want less orchestration boilerplate and easier extensions. |

`create_agent` does not eliminate LangGraph. It builds a graph-backed agent. The trade-off is that standard orchestration becomes less explicit in application code, so the UI should display the actual runtime events rather than imply that the custom nodes still exist.

## 1. Preserve the seams already in place

Keep these unchanged during the first migration:

- `create_helpdesk_tools(repository, employee_id)` in `agent-system/tools/helpdesk.py`. It binds identity in application code and exposes only read operations.
- `HelpdeskRepository` and its read-only SQLite connection.
- The current system prompt and tool descriptions.
- Conversation history management in Streamlit/CLI, initially passing the accumulated messages to each invocation.
- The existing demo prompts and data fixtures.

Do not use a user- or model-supplied employee ID as proof of authorization. Middleware limits do not replace tool-level authorization.

## 2. Add the direct LangChain dependency

`create_agent` is provided by the `langchain` package. Add a compatible LangChain v1 dependency (for example, `langchain>=1,<2`) using the project's package manager, then lock and sync dependencies. Keep `langgraph` and `langchain-openai` dependencies; `create_agent` uses LangGraph underneath and the project uses the OpenAI integration.

Before migration, inspect the installed package versions and run the existing suite. This separates dependency/API issues from behavior changes.

## 3. Replace the custom builder with `create_agent`

Keep `build_agent(settings, repository=None, *, model=None)` as the application boundary. This minimizes changes in the CLI, Streamlit code, and tests. Within it:

1. Construct or accept the repository as now.
2. Create the existing identity-bound tools.
3. Construct `ChatOpenAI(model=settings.model_name, temperature=0)` unless a model is injected for tests.
4. Build one `ToolCallLimitMiddleware` instance per tool, with that tool's exact registered name and its per-run budget.
5. Add `ModelCallLimitMiddleware` for the model-call/agent-loop budget.
6. Return `create_agent(model=chat_model, tools=tools, system_prompt=SYSTEM_PROMPT, middleware=middleware)`.

Illustrative shape (choose limits/defaults deliberately; these values are examples):

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)

middleware = [
    ModelCallLimitMiddleware(
        run_limit=settings.max_model_steps,
        exit_behavior="end",
    ),
    ToolCallLimitMiddleware(
        tool_name="get_ticket_status",
        run_limit=2,
        exit_behavior="continue",
    ),
    ToolCallLimitMiddleware(
        tool_name="list_my_tickets",
        run_limit=1,
        exit_behavior="continue",
    ),
    ToolCallLimitMiddleware(
        tool_name="check_leave_balance",
        run_limit=1,
        exit_behavior="continue",
    ),
]

agent = create_agent(
    model=chat_model,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    middleware=middleware,
)
```

`tool_name` must exactly match each tool's `.name`. The limit middleware counts calls to that named tool during an invocation (run). A separate middleware instance provides a separate budget for each tool. A `None` tool name is a global tool-call budget, not a per-tool budget.

`exit_behavior` controls what happens when a limit is reached. Use `"continue"` for tool limits when the desired behavior is to let the agent continue with the limit observation and explain it to the user. Use `"end"` when the desired policy is to stop the run. Use `"error"` only if callers are prepared to catch and present a failure. Verify the installed version's behavior with focused tests, especially for a model response containing multiple tool calls.

## 4. Distinguish and configure the two limits

There are two different budgets:

- **Per-tool run limit**: how many times one named tool may execute in one agent invocation. Configure it with that tool's `ToolCallLimitMiddleware(tool_name=..., run_limit=...)`.
- **Model-call run limit**: how many model calls can occur during that invocation, including the calls after tool results. Configure it with `ModelCallLimitMiddleware(run_limit=...)`.

They are independent. For example, a run can allow up to two status lookups and one leave lookup, while also limiting total assistant/model rounds to six. A tool execution is not itself a model call, but after tool output the agent may call the model again.

The current custom graph uses `settings.max_model_steps` and checks it after a model response that requests tools. With `ModelCallLimitMiddleware`, preserve the intended maximum and choose `exit_behavior` to match the old friendly stop response. Middleware can change the exact stop point/response semantics, so write a regression test instead of assuming the behavior is identical.

The Streamlit sidebar currently exposes one model-call maximum. To make tool limits user-configurable later, add a separate numeric control for each tool and include those values in the runtime cache key and session reset/config signature. Avoid labelling a model-call maximum as a tool-call maximum.

## 5. Invocation, state, persistence, and limits across turns

For a one-turn invocation, call the returned agent with the usual message state:

```python
result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
```

For follow-ups, continue passing the accumulated LangChain messages, as the app already does. A `run_limit` is per invocation, so it resets each turn.

Do not configure `thread_limit` unless the application introduces a LangGraph checkpointer and supplies a stable `thread_id` in the invocation config. The current Streamlit session's Python message list is short-term conversation context; it is not a persisted LangGraph thread. Even with a checkpointer, per-tool `thread_limit` is a different policy from the per-run cap and should be added only if a cross-turn budget is needed.

`config={"recursion_limit": N}` is a separate graph-execution safety bound, not a substitute for named per-tool budgets or model-call middleware. It can be retained as a final safety net if tested and clearly named.

## 6. Keep the Streamlit graph honest

The custom graph currently uses node names such as `assistant`, `tools`, and `step_limit`. A `create_agent` graph has framework-owned nodes (commonly `model` and `tools`) and middleware may add behavior. After migration:

1. Use the agent's streaming API to observe updates. LangChain v1 supports `stream_mode=["messages", "updates"]` with `version="v2"`; inspect update source names and messages in a small probe against the installed versions.
2. Update `_trace_turn` to handle the v2 event envelope (`chunk["type"]`, `chunk["data"]`) as well as AI tool calls and `ToolMessage` results.
3. Update the displayed graph from the observed node names. Do not show `assistant` or `step_limit` as runtime graph nodes if the built-in agent/middleware does not emit them.
4. If the UI wants a high-level graph such as `START → model ⇄ tools → END`, label it as a conceptual view. If it is intended to show actual runtime state, build it from observed graph metadata/events and mark the middleware stop outcome separately.
5. Continue to expose only observable execution events—tool name, arguments, tool result, active/completed node, and final response. Do not label hidden model reasoning as a trace.

Test the graph view for three paths: direct model answer (no tool), one tool then answer, and a blocked tool call after its limit.

## 7. Tests to preserve and add

Retain the repository and tool-scope tests. Adapt graph tests to the built-in agent's expected result/state, keeping injected fake models where supported. Add tests for:

- A normal ticket query calls the correct tool and returns a grounded model answer.
- The same named tool is blocked after its configured per-run limit.
- Different tools have independent counters/budgets.
- A blocked tool request does not execute its repository operation and produces a clear agent response (per selected `exit_behavior`).
- The model-call limit terminates a repeated tool loop.
- Tool-call messages and corresponding `ToolMessage` IDs remain valid, including when a response requests multiple tools.
- The Streamlit trace and graph show the actual `model`/`tools` events and completed route.
- Identity remains bound to the configured employee, regardless of chat text.

Run `uv run pytest agent-system/tests` after each stage. Compare answers and tool traces against the current custom-graph baseline before removing the old implementation.

## 8. Evolve toward multi-agent orchestration

For the planned IT/HR/Policy specialists, use `create_agent` for each specialist's local model/tool loop and retain an explicit outer LangGraph supervisor/router when routing and cross-agent workflow need to be visible:

```text
User → supervisor/router → IT create_agent → result ┐
                        → HR create_agent → result ├→ supervisor → user
                        → Policy create_agent → result ┘
```

- Give each specialist only its allowed tools. Configure its own per-tool limits and model-call limit on that specialist agent.
- Give the supervisor a per-run limit on each delegation tool (if delegation is represented as tools) and a model-call/hop limit for its routing loop.
- Treat specialist limits as local budgets. They do **not** automatically create one shared cap across all agents. If a whole-request/global tool budget is required, implement an explicit shared budget in outer graph state or a central policy layer and pass the remaining budget to each specialist; do not assume independent middleware instances aggregate counters.
- Keep authorization inside tools/repositories, including employee scoping; routing or middleware is not an authorization boundary.
- If agents need state across turns, introduce a checkpointer and stable thread identity deliberately. Otherwise, keep in-memory conversation context and per-run limits.

This gives a teachable progression: **custom LangGraph loop** (visible manual nodes) → **single `create_agent`** (built-in loop plus middleware) → **supervisor graph with `create_agent` specialists** (explicit multi-agent coordination with local controls).

## References

- [LangChain agents (`create_agent`)](https://docs.langchain.com/oss/python/langchain/agents)
- [Built-in middleware: model and tool call limits](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- [LangChain streaming](https://docs.langchain.com/oss/python/langchain/streaming)
- [LangGraph recursion limits](https://docs.langchain.com/oss/python/langgraph/graph-api#recursion-limit)
