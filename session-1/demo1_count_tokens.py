"""Demo 1: Tokenization - how text becomes tokens (no API key needed)."""
import sys

import tiktoken
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
MODEL = "gpt-4o-mini"
text = sys.argv[1] if len(sys.argv) > 1 else "Generative AI is transforming how we build software."

enc = tiktoken.encoding_for_model(MODEL)
ids = enc.encode(text)

COLORS = ["cyan", "magenta", "green", "yellow", "blue", "red"]

console.print(Panel(text, title="Input sentence", border_style="yellow"))
console.print(f"[bold]Model[/]     : {MODEL} (encoding: {enc.name})")
console.print(f"[bold]Characters[/]: [cyan]{len(text)}[/]")
console.print(f"[bold]Words[/]     : [cyan]{len(text.split())}[/]")
console.print(f"[bold]Tokens[/]    : [bold green]{len(ids)}[/]\n")

table = Table(title="Token breakdown", header_style="bold magenta")
table.add_column("#", justify="right")
table.add_column("Token ID", justify="right", style="cyan")
table.add_column("Token text")
highlighted = Text()
for i, tid in enumerate(ids, 1):
    piece = enc.decode([tid])
    color = COLORS[i % len(COLORS)]
    table.add_row(str(i), str(tid), Text(repr(piece), style=color))
    highlighted.append(piece, style=f"black on {color}")
console.print(table)

console.print("\n[bold]Tokens highlighted in the sentence:[/]")
console.print(highlighted)

console.print("\n[bold]Token IDs[/] :", ids)
console.print("[bold]Decoded[/]   :", enc.decode(ids))

# Rough cost illustration (example price: $0.15 per 1M input tokens)
console.print(f"\n[bold]Example cost[/] @ $0.15/1M tokens: [green]${len(ids) * 0.15 / 1_000_000:.8f}[/]")

# Show that rare/long words split into more tokens
words = Table(title="Tokens per word", header_style="bold magenta")
words.add_column("Word")
words.add_column("Count", justify="right")
words.add_column("Pieces")
for w in ["cat", "Generative", "unbelievably", "Supercalifragilistic", "नमस्ते"]:
    w_ids = enc.encode(w)
    style = "green" if len(w_ids) == 1 else "yellow" if len(w_ids) <= 3 else "red"
    words.add_row(w, f"[{style}]{len(w_ids)}[/]", str([enc.decode([t]) for t in w_ids]))
console.print()
console.print(words)
