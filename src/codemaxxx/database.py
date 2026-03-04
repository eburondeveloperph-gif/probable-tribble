"""CodeMaxxx — PostgreSQL long-term memory & conversation storage."""

import os
import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from .machine_uid import get_machine_uid

DB_NAME = os.environ.get("CODEMAXXX_DB_NAME", "codemaxxx")
DB_USER = os.environ.get("CODEMAXXX_DB_USER", "codemaxxx")
DB_PASS = os.environ.get("CODEMAXXX_DB_PASS", "codemaxxx")
DB_HOST = os.environ.get("CODEMAXXX_DB_HOST", "localhost")
DB_PORT = os.environ.get("CODEMAXXX_DB_PORT", "5432")

# The secret key the model must provide to write to long-term memory
MEMORY_WRITE_KEY = "MyMasterDontAllowMe"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS machines (
    machine_uid  VARCHAR(32) PRIMARY KEY,
    hostname     TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversations (
    id           SERIAL PRIMARY KEY,
    machine_uid  VARCHAR(32) REFERENCES machines(machine_uid),
    session_id   TEXT,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    model        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS memory (
    id           SERIAL PRIMARY KEY,
    machine_uid  VARCHAR(32) REFERENCES machines(machine_uid),
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    model        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(machine_uid, key)
);

CREATE INDEX IF NOT EXISTS idx_conv_machine ON conversations(machine_uid);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_memory_machine ON memory(machine_uid);
"""


class Database:
    """PostgreSQL-backed long-term memory for CodeMaxxx."""

    def __init__(self):
        self.machine_uid = get_machine_uid()
        self._conn: Optional[psycopg2.extensions.connection] = None

    def connect(self) -> bool:
        """Connect to PostgreSQL and initialize schema."""
        try:
            self._conn = psycopg2.connect(
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
                host=DB_HOST,
                port=DB_PORT,
            )
            self._conn.autocommit = True
            self._init_schema()
            self._register_machine()
            return True
        except Exception as e:
            self._conn = None
            return False

    def _init_schema(self):
        with self._conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)

    def _register_machine(self):
        import platform
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO machines (machine_uid, hostname)
                   VALUES (%s, %s)
                   ON CONFLICT (machine_uid) DO NOTHING""",
                (self.machine_uid, platform.node()),
            )

    @property
    def connected(self) -> bool:
        return self._conn is not None and not self._conn.closed

    # ── Conversations ─────────────────────────────────────────────

    def save_message(self, session_id: str, role: str, content: str, model: str = ""):
        """Save a conversation message."""
        if not self.connected:
            return
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO conversations (machine_uid, session_id, role, content, model)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (self.machine_uid, session_id, role, content, model),
                )
        except Exception:
            pass

    def get_recent_conversations(self, limit: int = 50) -> list[dict]:
        """Get recent conversations for this machine."""
        if not self.connected:
            return []
        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT role, content, model, session_id, created_at
                       FROM conversations
                       WHERE machine_uid = %s
                       ORDER BY created_at DESC LIMIT %s""",
                    (self.machine_uid, limit),
                )
                return list(reversed(cur.fetchall()))
        except Exception:
            return []

    # ── Long-term Memory (read: anyone, write: model with key) ────

    def read_memory(self, key: Optional[str] = None) -> list[dict]:
        """Read long-term memory. Anyone can read."""
        if not self.connected:
            return []
        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if key:
                    cur.execute(
                        """SELECT key, value, model, updated_at
                           FROM memory WHERE machine_uid = %s AND key = %s""",
                        (self.machine_uid, key),
                    )
                else:
                    cur.execute(
                        """SELECT key, value, model, updated_at
                           FROM memory WHERE machine_uid = %s
                           ORDER BY updated_at DESC""",
                        (self.machine_uid,),
                    )
                return cur.fetchall()
        except Exception:
            return []

    def write_memory(self, key: str, value: str, model: str, write_key: str) -> bool:
        """Write to long-term memory. Requires the secret write key."""
        if write_key != MEMORY_WRITE_KEY:
            return False
        if not self.connected:
            return False
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO memory (machine_uid, key, value, model, updated_at)
                       VALUES (%s, %s, %s, %s, NOW())
                       ON CONFLICT (machine_uid, key)
                       DO UPDATE SET value = EXCLUDED.value,
                                     model = EXCLUDED.model,
                                     updated_at = NOW()""",
                    (self.machine_uid, key, value, model),
                )
            return True
        except Exception:
            return False

    def delete_memory(self, key: str, write_key: str) -> bool:
        """Delete a memory entry. Requires the secret write key."""
        if write_key != MEMORY_WRITE_KEY:
            return False
        if not self.connected:
            return False
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """DELETE FROM memory WHERE machine_uid = %s AND key = %s""",
                    (self.machine_uid, key),
                )
            return True
        except Exception:
            return False

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
