import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "logsentinel.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            total_lines INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            warning_count INTEGER DEFAULT 0,
            critical_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            timestamp TEXT,
            level TEXT NOT NULL,       -- ERROR, WARNING, CRITICAL, INFO
            message TEXT NOT NULL,
            source TEXT,
            raw_line TEXT,
            signature TEXT,            -- hash para agrupar eventos iguais
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_events_level ON events(level);
        CREATE INDEX IF NOT EXISTS idx_events_file ON events(file_id);
        CREATE INDEX IF NOT EXISTS idx_events_sig ON events(signature);
        """)