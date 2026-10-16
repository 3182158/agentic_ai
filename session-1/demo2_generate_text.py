"""Demo 2: Text generation - how an LLM predicts the next token."""
import math

from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.table import Table

console = Console()
load_dotenv()  # loads OPENAI_API_KEY from .env
client = OpenAI()
MODEL = "gpt-4o-mini"
prompt = "The capital of France is"

# Part 1: next-token probabilities (the core of how an LLM works)
console.rule(f"[bold cyan]Part 1: Next-token probabilities for: '{prompt}'")
with console.status("[cyan]Calling the model..."):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": f"Complete the sentence: {prompt}"}],
        max_tokens=1,
        logprobs=True,
        top_logprobs=5,
    )
table = Table(header_style="bold magenta")
table.add_column("Token")
table.add_column("Probability", justify="right")
table.add_column("Bar")
for t in r.choices[0].logprobs.content[0].top_logprobs:
    pct = math.exp(t.logprob) * 100
    style = "green" if pct > 50 else "yellow" if pct > 5 else "red"
    table.add_row(repr(t.token), f"[{style}]{pct:6.2f}%[/]", f"[{style}]{'█' * round(pct / 2)}[/]")
console.print(table)

# Part 2: token-by-token streaming
console.rule("[bold cyan]Part 2: Streaming generation (one token chunk at a time)")
stream = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "Explain in 2 sentences how an LLM generates text."}],
    stream=True,
)
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        console.print(chunk.choices[0].delta.content, end="", style="green", markup=False, highlight=False)
console.print()

# Part 3: temperature changes creativity

# For OpenAI models, temperature ranges from 0 to 2, not 0 to 1. The 0 to 1 range is common in other providers (Anthropic, for example), which is probably why 1.5 looked wrong.
# 0: almost deterministic. The model nearly always picks the highest-probability token, so repeated runs give nearly the same output.
# 1: the default. Tokens are sampled according to their real probabilities.
# 1.5: the probabilities are flattened, so unlikely tokens get picked more often. The output is more random and creative, and it can get erratic.
# 2: the maximum, usually close to gibberish.


console.rule("[bold cyan]Part 3: Temperature effect")
story_prompt = "Write a one-line story about a robot."
for temp in (0.0, 1.5):
    console.print(f"\n[bold {'blue' if temp == 0 else 'red'}]temperature={temp}[/]")
    for _ in range(2):
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": story_prompt}],
            temperature=temp,
            max_tokens=40,
        )
        console.print("  -", r.choices[0].message.content.strip(), markup=False)

console.print(
    f"\n[dim]Usage (last call): {r.usage.prompt_tokens} prompt + {r.usage.completion_tokens} completion tokens[/]"
)
