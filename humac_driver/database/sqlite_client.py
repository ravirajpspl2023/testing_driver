import sqlite3
import json
import time
import uuid
import os
import threading
import logging
from humac_driver.const import SQLITE_DB_FILE


class SqliteConnection:
    def __init__(self, stream_name):
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        self.stream_name = stream_name
        self.group_name = "HumacDriver"
        self.db_file = SQLITE_DB_FILE
        self.lock = threading.Lock()
        self.conn = None

    def connect(self):
        try:
            db_dir = os.path.dirname(os.path.abspath(self.db_file))
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            self.conn = sqlite3.connect(self.db_file, check_same_thread=False, timeout=30)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA busy_timeout=30000;")
            self._init_db()
            self.logger.info(f"Successfully connected to SQLite: {self.db_file}")
            self.create_group()
            return self
        except Exception as e:
            self.logger.error(f"Failed to connect to SQLite: {e}")
            time.sleep(5)
            return self.connect()

    def _init_db(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stream TEXT NOT NULL,
                    message_id TEXT NOT NULL UNIQUE,
                    data TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    acked INTEGER NOT NULL DEFAULT 0,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    pending_since REAL,
                    pending_consumer TEXT
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_groups (
                    group_name TEXT PRIMARY KEY,
                    stream_name TEXT NOT NULL,
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            self.conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_stream_entries_pending
                ON stream_entries (stream, acked, deleted, pending_since)
                """
            )

    def create_group(self):
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO stream_groups (group_name, stream_name) VALUES (?, ?)"
                , (self.group_name, self.stream_name)
            )
            self.conn.commit()

    def xadd(self, stream, fields, id='*'):
        try:
            message_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            data = json.dumps(fields)
            created_at = time.time()
            with self.lock, self.conn:
                self.conn.execute(
                    "INSERT INTO stream_entries (stream, message_id, data, created_at) VALUES (?, ?, ?, ?)"
                    , (stream, message_id, data, created_at)
                )
                self.conn.commit()
            return message_id
        except Exception as e:
            self.logger.error(f"SQLite xadd failed: {e}")
            return None

    def xreadgroup(self, group, consumer, streams, count=1, block=0):
        stream_name = None
        if isinstance(streams, dict):
            stream_name = next(iter(streams.keys()))
        elif isinstance(streams, list) and streams:
            stream_name = streams[0]
        else:
            stream_name = self.stream_name

        end_time = time.time() + (block / 1000.0 if block else 0)
        while True:
            with self.lock, self.conn:
                idle_threshold = time.time() - 60
                rows = self.conn.execute(
                    """
                    SELECT message_id, data
                    FROM stream_entries
                    WHERE stream = ?
                      AND acked = 0
                      AND deleted = 0
                      AND (pending_since IS NULL OR pending_since <= ?)
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (stream_name, idle_threshold, count),
                ).fetchall()

                if rows:
                    messages = []
                    now = time.time()
                    for row in rows:
                        self.conn.execute(
                            """
                            UPDATE stream_entries
                            SET pending_since = ?, pending_consumer = ?
                            WHERE message_id = ?
                            """,
                            (now, consumer, row["message_id"]),
                        )
                        payload = json.loads(row["data"])
                        messages.append((row["message_id"], payload))
                    self.conn.commit()
                    return [(stream_name, messages)]

            if not block:
                return []
            if time.time() >= end_time:
                return []
            time.sleep(0.05)

    def xack(self, stream, group, message_id):
        with self.lock, self.conn:
            cursor = self.conn.execute(
                """
                UPDATE stream_entries
                SET acked = 1, pending_since = NULL, pending_consumer = NULL
                WHERE stream = ? AND message_id = ?
                """,
                (stream, message_id),
            )
            self.conn.commit()
            return cursor.rowcount

    def xdel(self, stream, message_id):
        with self.lock, self.conn:
            cursor = self.conn.execute(
                "DELETE FROM stream_entries WHERE stream = ? AND message_id = ?"
                , (stream, message_id)
            )
            self.conn.commit()
            return cursor.rowcount

    def ping(self):
        return True
