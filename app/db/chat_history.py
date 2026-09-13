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
            updated_at TEXT NOT NULL,
            is_favorite INTEGER NOT NULL DEFAULT 0
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sources (
                id TEXT PRIMARY KEY,
                chat_id TEXT DEFAULT 'global',
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                text_content TEXT,
                parsed_meta_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        try:
            
            fk_info = conn.execute("PRAGMA foreign_key_list(chat_sources);").fetchall()
            if fk_info:
                conn.execute("DROP TABLE IF EXISTS chat_sources;")
                conn.execute(
                    """
                    CREATE TABLE chat_sources (
                        id TEXT PRIMARY KEY,
                        chat_id TEXT DEFAULT 'global',
                        filename TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        text_content TEXT,
                        parsed_meta_json TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )
        except Exception:
            pass
        try:
            conn.execute(
                "ALTER TABLE chats ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            
            pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sources_chat_id ON chat_sources(chat_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC);")
        conn.commit()
        


def list_chats() -> List[Dict[str, Any]]:
    """Return all chat sessions ordered by most recently updated."""
    init_db()
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at, is_favorite
            FROM chats
            ORDER BY is_favorite DESC, updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    """Get chat metadata by ID."""
    init_db()
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, created_at, updated_at, is_favorite
            FROM chats
            WHERE id = ?
            """,
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

def toggle_favorite(chat_id: str) -> bool:
    """Переключить статус избранного для чата."""
    init_db()

    with _get_connection() as conn:
        row = conn.execute(
            "SELECT is_favorite FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()

        if not row:
            return False

        new_value = 0 if row["is_favorite"] else 1

        conn.execute(
            """
            UPDATE chats
            SET is_favorite = ?
            WHERE id = ?
            """,
            (new_value, chat_id),
        )
        conn.commit()

        return bool(new_value)


def delete_chat(chat_id: str) -> None:
    """Delete a chat session and its messages."""
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
        
        chat_row = conn.execute("SELECT id, title FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if not chat_row:
            
            auto_title = content.strip()[:40] + ("..." if len(content.strip()) > 40 else "")
            conn.execute(
                "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (chat_id, auto_title or "Новый диалог", now, now),
            )
        else:
            
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


def add_chat_source(
    filename: str,
    file_path: str,
    file_type: str,
    size_bytes: int,
    text_content: str,
    chat_id: Optional[str] = "global",
    parsed_meta: Optional[Dict[str, Any]] = None,
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Register an uploaded user file in global sandbox."""
    init_db()
    sid = source_id or str(uuid.uuid4())
    cid = chat_id or "global"
    now = datetime.now().isoformat()
    meta_json = json.dumps(parsed_meta, ensure_ascii=False) if parsed_meta else None

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO chat_sources
            (id, chat_id, filename, file_path, file_type, size_bytes, is_active, text_content, parsed_meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (sid, cid, filename, file_path, file_type, size_bytes, text_content, meta_json, now),
        )
        conn.commit()

    return {
        "id": sid,
        "chat_id": cid,
        "filename": filename,
        "file_path": file_path,
        "file_type": file_type,
        "size_bytes": size_bytes,
        "is_active": True,
        "text_content": text_content,
        "parsed_meta": parsed_meta or {},
        "created_at": now,
    }


def list_chat_sources(chat_id: Optional[str] = None, only_active: bool = False) -> List[Dict[str, Any]]:
    """Return sandbox files. Sources are globally accessible across all chats."""
    init_db()
    with _get_connection() as conn:
        if only_active:
            rows = conn.execute(
                """
                SELECT id, chat_id, filename, file_path, file_type, size_bytes, is_active, text_content, parsed_meta_json, created_at
                FROM chat_sources
                WHERE is_active = 1
                ORDER BY created_at ASC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, chat_id, filename, file_path, file_type, size_bytes, is_active, text_content, parsed_meta_json, created_at
                FROM chat_sources
                ORDER BY created_at ASC
                """
            ).fetchall()

        sources = []
        for r in rows:
            meta = {}
            if r["parsed_meta_json"]:
                try:
                    meta = json.loads(r["parsed_meta_json"])
                except Exception:
                    meta = {}
            sources.append({
                "id": r["id"],
                "chat_id": r["chat_id"],
                "filename": r["filename"],
                "file_path": r["file_path"],
                "file_type": r["file_type"],
                "size_bytes": r["size_bytes"],
                "is_active": bool(r["is_active"]),
                "text_content": r["text_content"],
                "parsed_meta": meta,
                "created_at": r["created_at"],
            })
        return sources


def get_chat_source(source_id: str) -> Optional[Dict[str, Any]]:
    """Get a single sandbox file metadata and content by ID."""
    init_db()
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, chat_id, filename, file_path, file_type, size_bytes, is_active, text_content, parsed_meta_json, created_at
            FROM chat_sources
            WHERE id = ?
            """,
            (source_id,),
        ).fetchone()
        if not row:
            return None

        meta = {}
        if row["parsed_meta_json"]:
            try:
                meta = json.loads(row["parsed_meta_json"])
            except Exception:
                meta = {}
        return {
            "id": row["id"],
            "chat_id": row["chat_id"],
            "filename": row["filename"],
            "file_path": row["file_path"],
            "file_type": row["file_type"],
            "size_bytes": row["size_bytes"],
            "is_active": bool(row["is_active"]),
            "text_content": row["text_content"],
            "parsed_meta": meta,
            "created_at": row["created_at"],
        }


def toggle_chat_source(source_id: str, is_active: Optional[bool] = None) -> Optional[bool]:
    """Toggle or set active status of sandbox file."""
    init_db()
    with _get_connection() as conn:
        if is_active is None:
            row = conn.execute("SELECT is_active FROM chat_sources WHERE id = ?", (source_id,)).fetchone()
            if not row:
                return None
            new_val = 0 if row["is_active"] else 1
        else:
            new_val = 1 if is_active else 0

        conn.execute("UPDATE chat_sources SET is_active = ? WHERE id = ?", (new_val, source_id))
        conn.commit()
        return bool(new_val)


def delete_chat_source(source_id: str) -> bool:
    """Delete a sandbox file from DB and disk."""
    init_db()
    source = get_chat_source(source_id)
    if not source:
        return False

    with _get_connection() as conn:
        conn.execute("DELETE FROM chat_sources WHERE id = ?", (source_id,))
        conn.commit()

    
    try:
        fpath = Path(source["file_path"])
        if fpath.exists():
            fpath.unlink()
    except Exception:
        pass

    return True

