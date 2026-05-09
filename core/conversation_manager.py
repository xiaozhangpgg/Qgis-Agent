import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qgis.core import QgsApplication

logger = logging.getLogger("QgisAgent")


@dataclass
class ConversationMessage:
    role: str
    content: str
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Conversation:
    id: str
    title: str
    created_at: float
    updated_at: float
    messages: List[ConversationMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationSummary:
    id: str
    title: str
    updated_at: float
    message_count: int
    preview: str

    @property
    def updated_at_display(self) -> str:
        from datetime import datetime
        dt = datetime.fromtimestamp(self.updated_at)
        return dt.strftime("%m-%d %H:%M")


class ConversationManager:
    """SQLite-backed conversation persistence."""

    def __init__(self):
        self._db_path = self._get_db_path()
        self._current_id: Optional[str] = None
        self._init_db()

    def _get_db_path(self) -> str:
        data_dir = os.path.join(
            QgsApplication.qgisSettingsDirPath(), "QgisAgent"
        )
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "conversations.db")

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                        ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages(conversation_id)
            """)
            conn.commit()

    def create_new(self) -> str:
        conv_id = f"conv_{int(time.time() * 1000)}"
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conv_id, "新对话", now, now),
            )
            conn.commit()
        self._current_id = conv_id
        return conv_id

    def get_current_id(self) -> Optional[str]:
        return self._current_id

    def save_message(self, conv_id: str, role: str, content: str,
                     metadata: Optional[Dict] = None):
        now = time.time()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, timestamp, metadata) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, role, content, now, meta_json),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conv_id),
            )
            conn.commit()

    def update_title(self, conv_id: str, title: str):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (title, conv_id),
            )
            conn.commit()

    def list_conversations(self) -> List[ConversationSummary]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC"
            ).fetchall()

            summaries = []
            for row in rows:
                msg_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                    (row["id"],),
                ).fetchone()[0]

                last_msg = conn.execute(
                    "SELECT content FROM messages WHERE conversation_id = ? "
                    "ORDER BY timestamp DESC LIMIT 1",
                    (row["id"],),
                ).fetchone()

                preview = ""
                if last_msg:
                    preview = last_msg[0][:80].replace("\n", " ")

                summaries.append(ConversationSummary(
                    id=row["id"],
                    title=row["title"],
                    updated_at=row["updated_at"],
                    message_count=msg_count,
                    preview=preview,
                ))
            return summaries

    def load_conversation(self, conv_id: str) -> Optional[Conversation]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if not row:
                return None

            msg_rows = conn.execute(
                "SELECT role, content, timestamp, metadata FROM messages "
                "WHERE conversation_id = ? ORDER BY timestamp",
                (conv_id,),
            ).fetchall()

            messages = []
            for mr in msg_rows:
                meta = json.loads(mr["metadata"]) if mr["metadata"] else {}
                messages.append(ConversationMessage(
                    role=mr["role"],
                    content=mr["content"],
                    timestamp=mr["timestamp"],
                    metadata=meta,
                ))

            conv_meta = json.loads(row["metadata"]) if row["metadata"] else {}
            self._current_id = conv_id

            return Conversation(
                id=row["id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                messages=messages,
                metadata=conv_meta,
            )

    def delete_conversation(self, conv_id: str):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()
        if self._current_id == conv_id:
            self._current_id = None

    def search_conversations(self, query: str) -> List[ConversationSummary]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            pattern = f"%{query}%"
            rows = conn.execute(
                "SELECT DISTINCT c.id, c.title, c.updated_at "
                "FROM conversations c "
                "LEFT JOIN messages m ON c.id = m.conversation_id "
                "WHERE c.title LIKE ? OR m.content LIKE ? "
                "ORDER BY c.updated_at DESC",
                (pattern, pattern),
            ).fetchall()

            summaries = []
            for row in rows:
                msg_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                    (row["id"],),
                ).fetchone()[0]

                last_msg = conn.execute(
                    "SELECT content FROM messages WHERE conversation_id = ? "
                    "ORDER BY timestamp DESC LIMIT 1",
                    (row["id"],),
                ).fetchone()

                preview = ""
                if last_msg:
                    preview = last_msg[0][:80].replace("\n", " ")

                summaries.append(ConversationSummary(
                    id=row["id"],
                    title=row["title"],
                    updated_at=row["updated_at"],
                    message_count=msg_count,
                    preview=preview,
                ))
            return summaries
