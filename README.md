# Generative AI Demos

Three standalone demos showing how LLMs work. Output is colored with `rich`.

## Setup

1. Install dependencies (Python 3.12+, [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

2. Add your OpenAI key. Copy `.env.example` to `.env` and fill it in:

   ```bash
   cp .env.example .env
   # OPENAI_API_KEY=sk-...
   ```

   `.env` is git-ignored. Demo 1 does not need a key.

## Demos

| # | File | What it shows | Needs API key |
|---|------|---------------|---------------|
| 1 | `session-1/demo1_count_tokens.py` | Text split into tokens, token IDs, per-word token counts, example cost | No |
| 2 | `session-1/demo2_generate_text.py` | Next-token probabilities, streaming output, temperature effect | Yes |
| 3 | `session-1/demo3_structured_output.py` | Extracting schema-validated JSON (Pydantic) from an email | Yes |
| 4 | `agent-system/` | Session 1 LangGraph helpdesk agent with read-only SQLite tools and in-memory conversation context | Yes |

```bash
uv run session-1/demo1_count_tokens.py "Your own sentence here"
uv run session-1/demo2_generate_text.py
uv run session-1/demo3_structured_output.py
uv run python agent-system/cli.py
```

See [agent-system/README.md](agent-system/README.md) for the agent architecture, configuration, sample prompts, security boundaries, and API-key-free tests. Run its tests with `uv run pytest agent-system/tests`.

## Notes

- All demos use `gpt-4o-mini`; change `MODEL` at the top of each file to switch.
- Temperature for OpenAI models ranges from 0 to 2 (0 is near-deterministic, 1 is the default).
