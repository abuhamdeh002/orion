"""Long-term facts. Keyword search (SQLite FTS5) always works; Ollama embeddings add meaning when available.

Recall must be deterministic across restarts and must never stall a turn:
* FTS5 ranks by BM25 and needs nothing outside the database.
* Embeddings are tagged with the model that made them and only compared with
  vectors from the same model. When Ollama is down, recall skips them at once
  instead of waiting on a timeout every turn.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import uuid
from datetime import datetime, timezone

import httpx

from storage.database import Database

EMBED_MODEL = "nomic-embed-text"
_EMBED_RETRY_SECONDS = 60.0
_SEMANTIC_FLOOR = 0.55

_MEMORY_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding_json TEXT,
    created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(id UNINDEXED, text, tokenize = 'porter unicode61');
"""

_STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "and", "or", "in", "on", "at", "for",
    "with", "my", "me", "i", "you", "your", "what", "who", "whats", "where", "when", "how", "do", "does",
    "did", "it", "this", "that", "can", "could", "would", "should", "please", "tell", "about", "know",
}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _terms(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower().replace("'s", ""))
    return [word for word in words if len(word) > 1 and word not in _STOP]


class MemoryRepository:
    def __init__(self, database: Database, ollama_base_url: str = "http://127.0.0.1:11434") -> None:
        self.database = database
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self._embed_down_until = 0.0
        self._embed_lock = threading.Lock()
        with database._lock:
            database.connection.executescript(_MEMORY_SQL)
            columns = {row[1] for row in database.connection.execute("PRAGMA table_info(memories)")}
            if "embedding_model" not in columns:
                database.connection.execute("ALTER TABLE memories ADD COLUMN embedding_model TEXT")
            # Old rows were embedded with a per-process hash, which is meaningless now. Drop those vectors.
            database.connection.execute(
                "UPDATE memories SET embedding_json = NULL WHERE embedding_model IS NULL AND embedding_json IS NOT NULL"
            )
            database.connection.execute(
                "INSERT INTO memories_fts (id, text) SELECT id, text FROM memories "
                "WHERE id NOT IN (SELECT id FROM memories_fts)"
            )
            database.connection.commit()

    # -- embeddings (optional) ----------------------------------------------------------------

    def embed(self, text: str) -> list[float] | None:
        with self._embed_lock:
            if time.monotonic() < self._embed_down_until:
                return None
        try:
            with httpx.Client(timeout=1.5) as client:
                response = client.post(
                    f"{self.ollama_base_url}/api/embeddings",
                    # On the CPU: on a small graphics card the embedder would push the chat model off the GPU.
                    json={"model": EMBED_MODEL, "prompt": text, "keep_alive": "30m", "options": {"num_gpu": 0}},
                )
            if response.status_code == 200:
                vector = response.json().get("embedding")
                if isinstance(vector, list) and vector:
                    return [float(item) for item in vector]
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        with self._embed_lock:
            self._embed_down_until = time.monotonic() + _EMBED_RETRY_SECONDS
        return None

    # -- writes -------------------------------------------------------------------------------

    def remember(self, text: str, kind: str = "fact") -> str:
        cleaned = text.strip()
        memory_id = str(uuid.uuid4())
        vector = self.embed(cleaned)
        with self.database._lock:
            self.database.connection.execute(
                "INSERT INTO memories (id, kind, text, embedding_json, embedding_model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    memory_id,
                    kind,
                    cleaned,
                    json.dumps(vector) if vector else None,
                    EMBED_MODEL if vector else None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self.database.connection.execute("INSERT INTO memories_fts (id, text) VALUES (?, ?)", (memory_id, cleaned))
            self.database.connection.commit()
        return memory_id

    def forget(self, memory_id: str) -> bool:
        with self.database._lock:
            cursor = self.database.connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self.database.connection.execute("DELETE FROM memories_fts WHERE id = ?", (memory_id,))
            self.database.connection.commit()
            return cursor.rowcount > 0

    # -- reads --------------------------------------------------------------------------------

    def list_all(self) -> list[dict[str, str]]:
        with self.database._lock:
            rows = self.database.connection.execute(
                "SELECT id, kind, text, created_at FROM memories ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def recall(self, query: str, limit: int = 4) -> list[dict[str, str]]:
        ranked: dict[str, float] = {}
        rows: dict[str, dict[str, str]] = {}
        terms = _terms(query)
        if terms:
            match = " OR ".join(f'"{term}"*' for term in terms)
            with self.database._lock:
                found = self.database.connection.execute(
                    "SELECT m.id, m.kind, m.text, bm25(memories_fts) AS score "
                    "FROM memories_fts JOIN memories m ON m.id = memories_fts.id "
                    "WHERE memories_fts MATCH ? ORDER BY score LIMIT 20",
                    (match,),
                ).fetchall()
            for position, row in enumerate(found):
                ranked[row["id"]] = 1.0 - position / 40.0
                rows[row["id"]] = {"id": row["id"], "kind": row["kind"], "text": row["text"]}
        vector = self.embed(query) if query.strip() else None
        if vector:
            with self.database._lock:
                stored = self.database.connection.execute(
                    "SELECT id, kind, text, embedding_json FROM memories WHERE embedding_model = ?", (EMBED_MODEL,)
                ).fetchall()
            for row in stored:
                try:
                    similarity = _cosine(vector, json.loads(row["embedding_json"] or "[]"))
                except json.JSONDecodeError:
                    continue
                if similarity >= _SEMANTIC_FLOOR:
                    ranked[row["id"]] = max(ranked.get(row["id"], 0.0), similarity) + (0.25 if row["id"] in ranked else 0.0)
                    rows[row["id"]] = {"id": row["id"], "kind": row["kind"], "text": row["text"]}
        order = sorted(ranked, key=ranked.get, reverse=True)
        return [rows[memory_id] for memory_id in order[:limit]]
