from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_key TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    title TEXT NOT NULL,
    contact_name TEXT,
    latest_preview TEXT,
    last_activity_at TEXT,
    unread_count INTEGER DEFAULT 0,
    pinned INTEGER DEFAULT 0,
    archived INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(app_key, chat_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    source_key TEXT UNIQUE,
    role TEXT NOT NULL,
    direction TEXT NOT NULL,
    content TEXT NOT NULL,
    sender_name TEXT,
    sender_id TEXT,
    origin_app TEXT,
    is_ai_generated INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    source_key TEXT UNIQUE,
    incoming_message_id INTEGER,
    reply_text TEXT NOT NULL,
    mode TEXT,
    risk_level TEXT,
    decision TEXT,
    provider TEXT,
    model TEXT,
    status TEXT DEFAULT 'pending',
    evidence_json TEXT,
    memory_json TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    published_at TEXT,
    publish_error TEXT,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AppDataStore:
    """SQLite 持久化存储"""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _get_or_create_conversation(
        self,
        *,
        app_key: str,
        chat_id: str,
        title: str,
        contact_name: str | None = None,
    ) -> int:
        now = _now()
        self._conn.execute(
            """
            INSERT INTO conversations (app_key, chat_id, title, contact_name, last_activity_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_key, chat_id) DO UPDATE SET
                title=excluded.title,
                last_activity_at=excluded.last_activity_at,
                updated_at=excluded.updated_at
            """,
            (app_key, chat_id, title, contact_name, now, now, now),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM conversations WHERE app_key=? AND chat_id=?",
            (app_key, chat_id),
        ).fetchone()
        return row["id"]

    def record_message(
        self,
        *,
        app_key: str,
        chat_id: str,
        title: str,
        contact_name: str,
        content: str,
        role: str,
        direction: str,
        sender_name: str = "",
        sender_id: str = "",
        origin_app: str = "",
        is_ai_generated: bool = False,
        source_key: str = "",
        created_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        import json
        conv_id = self._get_or_create_conversation(
            app_key=app_key, chat_id=chat_id, title=title, contact_name=contact_name
        )
        now = created_at or _now()
        try:
            cursor = self._conn.execute(
                """
                INSERT INTO messages
                    (conversation_id, source_key, role, direction, content, sender_name,
                     sender_id, origin_app, is_ai_generated, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conv_id, source_key, role, direction, content, sender_name,
                    sender_id, origin_app, int(is_ai_generated), now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            self._conn.commit()
            return cursor.lastrowid or 0
        except sqlite3.IntegrityError:
            row = self._conn.execute(
                "SELECT id FROM messages WHERE source_key=?", (source_key,)
            ).fetchone()
            return row["id"] if row else 0

    def record_suggestion(
        self,
        *,
        app_key: str,
        chat_id: str,
        title: str,
        contact_name: str,
        reply_text: str,
        mode: str = "hybrid",
        risk_level: str = "low",
        decision: str = "auto_send",
        provider: str = "",
        model: str = "",
        source_key: str = "",
        incoming_message_id: int = 0,
        evidence: list | None = None,
        memory: dict | None = None,
        status: str = "pending",
    ) -> int:
        import json
        conv_id = self._get_or_create_conversation(
            app_key=app_key, chat_id=chat_id, title=title, contact_name=contact_name
        )
        try:
            cursor = self._conn.execute(
                """
                INSERT INTO suggestions
                    (conversation_id, source_key, incoming_message_id, reply_text, mode,
                     risk_level, decision, provider, model, status, evidence_json, memory_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conv_id, source_key, incoming_message_id, reply_text, mode,
                    risk_level, decision, provider, model, status,
                    json.dumps(evidence or [], ensure_ascii=False),
                    json.dumps(memory or {}, ensure_ascii=False),
                    _now(),
                ),
            )
            self._conn.commit()
            return cursor.lastrowid or 0
        except sqlite3.IntegrityError:
            row = self._conn.execute(
                "SELECT id FROM suggestions WHERE source_key=?", (source_key,)
            ).fetchone()
            return row["id"] if row else 0

    def update_suggestion_status(
        self,
        suggestion_id: int,
        *,
        status: str,
        publish_error: str = "",
    ) -> None:
        self._conn.execute(
            "UPDATE suggestions SET status=?, publish_error=?, reviewed_at=? WHERE id=?",
            (status, publish_error, _now(), suggestion_id),
        )
        self._conn.commit()

    def mark_suggestion_published(self, suggestion_id: int) -> None:
        self._conn.execute(
            "UPDATE suggestions SET status='published', published_at=? WHERE id=?",
            (_now(), suggestion_id),
        )
        self._conn.commit()

    def get_conversations(self, app_key: str | None = None, limit: int = 50) -> list[dict]:
        if app_key:
            rows = self._conn.execute(
                "SELECT * FROM conversations WHERE app_key=? ORDER BY last_activity_at DESC LIMIT ?",
                (app_key, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM conversations ORDER BY last_activity_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_messages(self, conversation_id: int, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_pending_suggestions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT s.*, c.title, c.app_key, c.chat_id FROM suggestions s "
            "JOIN conversations c ON s.conversation_id = c.id "
            "WHERE s.status='pending' ORDER BY s.created_at DESC LIMIT 20"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
