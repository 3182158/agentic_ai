from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from agents.agent import build_agent
from build_database import build_database
from config import Settings
from data.repository import HelpdeskRepository
from domain import HelpdeskContext
from memory.long_term import LongTermMemory


class RecordingModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.prompts.append(str(messages[0].content))
        return AIMessage(content="ok")


def test_memory_is_scoped_per_employee_and_rejects_secrets(tmp_path: Path) -> None:
    memory = LongTermMemory(tmp_path / "m.sqlite3")
    assert memory.remember("E104", "Uses a MacBook, works remotely") == "Saved."
    assert memory.remember("E104", "my password is hunter2").startswith("Not saved")
    assert memory.list("E105") == []
    (memory_id, _), = memory.list("E104")
    assert not memory.forget("E105", memory_id)
    assert memory.forget("E104", memory_id)


def test_saved_memory_reaches_prompt_in_a_new_thread(tmp_path: Path) -> None:
    database = tmp_path / "helpdesk.sqlite3"
    build_database(database)
    memory = LongTermMemory(tmp_path / "m.sqlite3")
    memory.remember("E104", "Uses a MacBook")
    model = RecordingModel()
    app = build_agent(
        Settings(database, "E104", "test", 4),
        HelpdeskRepository(database),
        model=model,
        long_term_memory=memory,
    )

    app.invoke(
        {"messages": [HumanMessage(content="VPN is failing")]},
        context=HelpdeskContext(employee_id="E104"),
    )

    assert "Uses a MacBook" in model.prompts[0]
