from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.conversation_manager import ChatMessage
from storage.conversation_repository import ConversationRepository
from storage.database import Database


def test_messages_round_trip_and_prune(tmp_path) -> None:
    database = Database(tmp_path / "orion.db")
    repo = ConversationRepository(database)
    old = ChatMessage(
        role="user",
        content="old",
        created_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    recent = ChatMessage(role="assistant", content="recent", tool_call_id="c1", tool_calls=[{"id": "c1"}])
    repo.save(old)
    repo.save(recent)
    loaded = repo.load_recent(10)
    assert [item.content for item in loaded] == ["old", "recent"]
    assert loaded[1].tool_call_id == "c1"
    assert loaded[1].tool_calls == [{"id": "c1"}]
    removed = repo.prune(30)
    assert removed == 1
    assert [item.content for item in repo.load_recent(10)] == ["recent"]
    repo.clear()
    assert repo.load_recent(10) == []
    database.close()
