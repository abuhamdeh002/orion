"""Memory recall is deterministic and survives restarts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from storage.database import Database
from storage.memory_repository import MemoryRepository

_OFFLINE = "http://127.0.0.1:9"


def test_keyword_recall_finds_people_and_preferences(tmp_path: Path) -> None:
    database = Database(tmp_path / "m.db")
    memory = MemoryRepository(database, _OFFLINE)
    memory.remember("My sister is Lina.")
    memory.remember("I prefer tea over coffee.")
    memory.remember("The desk plant is named Fern.")
    assert memory.recall("who's my sister?")[0]["text"] == "My sister is Lina."
    assert memory.recall("do I like coffee")[0]["text"] == "I prefer tea over coffee."
    assert memory.recall("hello there") == []
    database.close()


def test_recall_survives_a_restart_with_a_different_hash_seed(tmp_path: Path) -> None:
    path = tmp_path / "m.db"
    database = Database(path)
    MemoryRepository(database, _OFFLINE).remember("My sister is Lina.")
    database.close()
    script = (
        "from pathlib import Path; from storage.database import Database; "
        "from storage.memory_repository import MemoryRepository; "
        f"m = MemoryRepository(Database(Path(r'{path}')), '{_OFFLINE}'); "
        "print(m.recall('sister')[0]['text'])"
    )
    env = {**os.environ, "PYTHONHASHSEED": "12345"}
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "My sister is Lina.", out.stderr


def test_dead_ollama_is_not_asked_twice(tmp_path: Path) -> None:
    database = Database(tmp_path / "m.db")
    memory = MemoryRepository(database, _OFFLINE)
    assert memory.embed("x") is None
    assert memory._embed_down_until > 0
    database.close()


def test_facts_are_captured_from_plain_statements(tmp_path: Path) -> None:
    from core.memory_capture import capture, facts_in

    assert facts_in("By the way, my sister is Lina.") == ["My sister is Lina"]
    assert facts_in("I prefer tea over coffee") == ["I prefer tea over coffee"]
    assert facts_in("is my sister home?") == []
    assert facts_in("remind me to call my sister is Lina") == []
    assert facts_in("what's the weather") == []

    database = Database(tmp_path / "m.db")
    memory = MemoryRepository(database, _OFFLINE)
    assert capture(memory, "my sister is Lina") == ["My sister is Lina"]
    assert capture(memory, "my sister is Lina") == []
    assert memory.list_all()[0]["kind"] == "auto"
    database.close()
