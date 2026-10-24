"""SQLite event log. One row per decision; the full event record is stored as JSON.

Helpers for scoring (Samhita): events_since() for velocity/cluster windows,
consumer_events() for a consumer's history, last_browse() for the too_fast rule.
"""

import json
import os
import sqlite3
import threading
import time

DB_PATH = os.environ.get("GATEWAY_DB_PATH", "gateway/data/events.db")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_last_browse: dict[tuple[str, str], float] = {}


def init(path: str = DB_PATH) -> None:
    global _conn
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _conn = sqlite3.connect(path, check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            epoch REAL NOT NULL,
            agent_keyid TEXT,
            consumer_id TEXT,
            decision TEXT,
            scenario TEXT,
            body TEXT NOT NULL
        )"""
    )
    _conn.execute("CREATE INDEX IF NOT EXISTS ix_events_epoch ON events(epoch)")
    _conn.execute("CREATE INDEX IF NOT EXISTS ix_events_consumer ON events(consumer_id)")
    _conn.commit()


def insert_event(event: dict) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO events (request_id, ts, epoch, agent_keyid, consumer_id, decision, scenario, body) VALUES (?,?,?,?,?,?,?,?)",
            (event["request_id"], event["ts"], time.time(), event.get("agent_keyid"), event.get("consumer_id"),
             event.get("decision"), event.get("scenario"), json.dumps(event)),
        )
        _conn.commit()


def _rows(sql: str, args: tuple) -> list[dict]:
    with _lock:
        return [json.loads(r[0]) for r in _conn.execute(sql, args).fetchall()]


def recent_events(limit: int = 100) -> list[dict]:
    """Newest first."""
    return _rows("SELECT body FROM events ORDER BY seq DESC LIMIT ?", (limit,))


def events_since(seconds: float) -> list[dict]:
    """All events in the last `seconds`, oldest first."""
    return _rows("SELECT body FROM events WHERE epoch >= ? ORDER BY seq", (time.time() - seconds,))


def consumer_events(consumer_id: str) -> list[dict]:
    """Every event for this consumer, oldest first."""
    return _rows("SELECT body FROM events WHERE consumer_id = ? ORDER BY seq", (consumer_id,))


def all_events() -> list[dict]:
    return _rows("SELECT body FROM events ORDER BY seq", ())


def record_browse(keyid: str, consumer_id: str) -> None:
    _last_browse[(keyid, consumer_id)] = time.time()


def last_browse(keyid: str, consumer_id: str) -> float | None:
    """Unix time of this (key, consumer)'s last signed /browse, or None."""
    return _last_browse.get((keyid, consumer_id))


def clear() -> None:
    """Wipe the log (used by the simulator's clean start)."""
    with _lock:
        _conn.execute("DELETE FROM events")
        _conn.commit()
    _last_browse.clear()
