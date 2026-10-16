"""Demo 3: Structured output - get validated JSON that matches a Pydantic schema."""
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()
load_dotenv()  # loads OPENAI_API_KEY from .env
client = OpenAI()
MODEL = "gpt-4o-mini"


class Task(BaseModel):
    title: str
    priority: Literal["low", "medium", "high"]


class Email(BaseModel):
    sender_name: str
    sentiment: Literal["positive", "neutral", "negative"]
    summary: str
    action_items: list[Task]


email_text = """
Hi team, this is Amr. The production deployment failed again last night and
customers are angry. Please fix the database connection issue ASAP, and send an
update to the client by tomorrow. Also, schedule a retro next week.
"""

console.print(Panel(email_text.strip(), title="Input email (unstructured)", border_style="yellow"))

with console.status("[cyan]Calling the model..."):
    completion = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Extract structured information from the email."},
            {"role": "user", "content": email_text},
        ],
        response_format=Email,
    )

result: Email = completion.choices[0].message.parsed

console.print(Panel(
    Syntax(result.model_dump_json(indent=2), "json", theme="monokai"),
    title="Structured JSON output",
    border_style="green",
))

SENTIMENT_COLOR = {"positive": "green", "neutral": "yellow", "negative": "red"}
PRIORITY_COLOR = {"low": "green", "medium": "yellow", "high": "bold red"}

console.print("\n[bold cyan]Typed Python object[/]")
console.print(f"[bold]Sender   :[/] {result.sender_name}")
color = SENTIMENT_COLOR[result.sentiment]
console.print(f"[bold]Sentiment:[/] [{color}]{result.sentiment}[/]")
console.print(f"[bold]Summary  :[/] {result.summary}\n")

table = Table(title="Action items", header_style="bold magenta")
table.add_column("#", justify="right")
table.add_column("Priority")
table.add_column("Task")
for i, t in enumerate(result.action_items, 1):
    table.add_row(str(i), f"[{PRIORITY_COLOR[t.priority]}]{t.priority.upper()}[/]", t.title)
console.print(table)
