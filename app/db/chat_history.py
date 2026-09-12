"""SQLite storage for chat sessions and message history.

Provides persistent chat history across server restarts for the Sber Meridian RAG Assistant.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_DIR = Path("data")
DB_PATH = DB_DIR / "chat_history.db"


def _get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db() -> None:
    """Initialize database tables if they do not exist."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                html_content TEXT,
                sources_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC);")
        conn.commit()


def list_chats() -> List[Dict[str, Any]]:
    """Return all chat sessions ordered by most recently updated."""
    init_db()
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    """Get chat metadata by ID."""
    init_db()
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None


def create_chat(chat_id: Optional[str] = None, title: Optional[str] = None) -> str:
    """Create a new chat session and return its ID."""
    init_db()
    cid = chat_id or str(uuid.uuid4())
    ctitle = title.strip() if title and title.strip() else "Новый диалог"
    now = datetime.now().isoformat()
    with _get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, ctitle, now, now),
        )
        conn.commit()
    return cid


def update_chat_title(chat_id: str, title: str) -> None:
    """Update title of a chat session."""
    init_db()
    now = datetime.now().isoformat()
    with _get_connection() as conn:
        conn.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (title.strip(), now, chat_id),
        )
        conn.commit()


def delete_chat(chat_id: str) -> None:
    """Delete a chat session and all its messages."""
    init_db()
    with _get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        conn.commit()


def add_message(
    chat_id: str,
    role: str,
    content: str,
    html_content: Optional[str] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Add a message to a chat session. Automatically initializes chat or updates its title on first turn."""
    init_db()
    now = datetime.now().isoformat()
    mid = str(uuid.uuid4())
    sources_json = json.dumps(sources, ensure_ascii=False) if sources is not None else None

    with _get_connection() as conn:
        # Check if chat exists
        chat_row = conn.execute("SELECT id, title FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if not chat_row:
            # Auto-create chat
            auto_title = content.strip()[:40] + ("..." if len(content.strip()) > 40 else "")
            conn.execute(
                "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (chat_id, auto_title or "Новый диалог", now, now),
            )
        else:
            # If title is default and user sent first message, update title
            if role == "user" and chat_row["title"] in ("Новый диалог", "Новый чат", ""):
                auto_title = content.strip()[:40] + ("..." if len(content.strip()) > 40 else "")
                conn.execute(
                    "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                    (auto_title, now, chat_id),
                )
            else:
                conn.execute(
                    "UPDATE chats SET updated_at = ? WHERE id = ?",
                    (now, chat_id),
                )

        conn.execute(
            """
            INSERT INTO messages (id, chat_id, role, content, html_content, sources_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (mid, chat_id, role, content, html_content, sources_json, now),
        )
        conn.commit()

    return {
        "id": mid,
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "html_content": html_content,
        "sources": sources or [],
        "created_at": now,
    }


def get_chat_messages(chat_id: str) -> List[Dict[str, Any]]:
    """Get all messages for a given chat session in chronological order."""
    init_db()
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, chat_id, role, content, html_content, sources_json, created_at
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (chat_id,),
        ).fetchall()

        messages = []
        for r in rows:
            sources = []
            if r["sources_json"]:
                try:
                    sources = json.loads(r["sources_json"])
                except Exception:
                    sources = []
            messages.append(
                {
                    "id": r["id"],
                    "chat_id": r["chat_id"],
                    "role": r["role"],
                    "content": r["content"],
                    "html_content": r["html_content"],
                    "sources": sources,
                    "created_at": r["created_at"],
                }
            )
        return messages
