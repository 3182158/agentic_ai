from cli import _content_as_text, _create_input_bindings, parse_command
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.keys import Keys


def test_parse_command_is_case_insensitive_and_accepts_arguments() -> None:
    assert parse_command("  /HeLp  ") == ("help", "")
    assert parse_command("/model test-model") == ("model", "test-model")


def test_parse_command_ignores_regular_chat_messages() -> None:
    assert parse_command("What is my leave balance?") is None


def test_content_as_text_handles_langchain_text_blocks() -> None:
    content = [
        {"type": "text", "text": "First paragraph."},
        {"type": "image", "url": "ignored"},
        {"type": "text", "text": "Second paragraph."},
    ]

    assert _content_as_text(content) == "First paragraph.\nSecond paragraph."


def test_enter_and_shift_enter_are_distinct_input_keys() -> None:
    assert ANSI_SEQUENCES["\x1b[27;2;13~"] == Keys.ControlJ
    assert ANSI_SEQUENCES["\x1b[13;2u"] == Keys.ControlJ
    assert ANSI_SEQUENCES["\x0a"] == Keys.ControlM
    bindings = _create_input_bindings()
    assert bindings.get_bindings_for_keys((Keys.ControlM,))
    assert bindings.get_bindings_for_keys((Keys.ControlJ,))