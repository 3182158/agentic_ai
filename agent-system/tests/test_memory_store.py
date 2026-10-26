import pytest

from memory.store import ConversationNotFound, ConversationStore


@pytest.fixture
def store(tmp_path):
    return ConversationStore(tmp_path / "memory.sqlite3")


def test_ownership_is_enforced(store):
    thread = store.create_conversation("E104")
    with pytest.raises(ConversationNotFound):
        store.get_conversation(thread, "E105")
    with pytest.raises(ConversationNotFound):
        store.add_message(thread, "E105", "user", "hi")
    with pytest.raises(ConversationNotFound):
        store.get_messages(thread, "E105")
    assert store.list_conversations("E105") == []


def test_title_set_from_first_message_and_listing_order(store):
    first = store.create_conversation("E104")
    second = store.create_conversation("E104")
    store.add_message(first, "E104", "user", "VPN keeps disconnecting")
    assert store.get_conversation(first, "E104")["title"] == "VPN keeps disconnecting"
    assert [c["thread_id"] for c in store.list_conversations("E104")] == [first, second]


def test_search_is_scoped_and_escapes_wildcards(store):
    mine = store.create_conversation("E104")
    other = store.create_conversation("E105")
    store.add_message(mine, "E104", "user", "100% printer problem")
    store.add_message(other, "E105", "user", "printer secret")
    assert [h["thread_id"] for h in store.search("E104", "printer")] == [mine]
    assert store.search("E104", "%") != []
    assert store.search("E104", "_") == []
    assert store.search("E104", "  ") == []


def test_analytics_and_soft_delete(store):
    thread = store.create_conversation("E104")
    store.add_message(thread, "E104", "user", "tickets?")
    store.add_message(thread, "E104", "assistant", "ok", tool_names=["list_my_tickets"])
    stats = store.analytics("E104")
    assert stats["conversations"] == 1
    assert stats["user_messages"] == 1
    assert stats["tool_usage"] == {"list_my_tickets": 1}
    assert store.analytics("E105")["conversations"] == 0

    store.delete_conversation(thread, "E104")
    assert store.list_conversations("E104") == []
    assert store.analytics()["conversations"] == 0
