"""GoBD-Protokollierung (Audit-Log): wer, wann, was.

Jeder Eintrag wird per fortlaufender SHA-256-Kette mit dem vorherigen verknüpft
(prev_hash → entry_hash). Damit lässt sich nachträgliches Ändern/Löschen einzelner
Einträge erkennen – ein anerkannter technischer Nachweis der Unveränderbarkeit
(GoBD), auch dort, wo Dateisystem-Rechte gegen einen Administrator nicht greifen.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import sqlite3

from . import config


def entry_hash(prev_hash: str, ts: str, user: str, action: str,
               entity: str, entity_id: str, detail: str) -> str:
    """SHA-256 über den Vorgänger-Hash + alle Inhaltsfelder dieses Eintrags."""
    payload = "␟".join((prev_hash or "", ts or "", user or "", action or "",
                             entity or "", str(entity_id or ""), detail or ""))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log(conn: sqlite3.Connection, action: str, entity: str = "", entity_id="",
        detail: str = "", user: str | None = None) -> None:
    user = user or config.CURRENT_USER
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = (row[0] if row else "") or ""
    h = entry_hash(prev, ts, user, action, entity, str(entity_id), detail)
    conn.execute(
        "INSERT INTO audit_log (ts, user, action, entity, entity_id, detail,"
        " prev_hash, entry_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, user, action, entity, str(entity_id), detail, prev, h),
    )


def verify_chain(conn: sqlite3.Connection) -> dict:
    """Prüft die gesamte Hash-Kette. Gibt {ok, count, broken_id} zurück."""
    prev = ""
    count = 0
    for r in conn.execute(
            "SELECT id, ts, user, action, entity, entity_id, detail, prev_hash, entry_hash"
            " FROM audit_log ORDER BY id ASC").fetchall():
        count += 1
        expected = entry_hash(prev, r[1], r[2], r[3], r[4], r[5], r[6])
        if (r[7] or "") != prev or (r[8] or "") != expected:
            return {"ok": False, "count": count, "broken_id": r[0]}
        prev = r[8]
    return {"ok": True, "count": count, "broken_id": None}
