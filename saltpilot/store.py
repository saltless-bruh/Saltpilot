"""GraphStore — thin persistence over SQLite (WAL). Task 0.4 / Requirement 5.

The schema is the *minimal* graph the full typed node/edge model grows from. Provenance and a
`source` provenance-class live on `interpretation` from day one so the later write-back /
quarantine gate (Copilot Section 4.4) is a policy change, not a schema migration. All writes go
through this one path (single-writer discipline, R5.4).

v1 implements the schema + engagement upsert here; asset/finding/interpretation upserts and
`facts_for_query` land in their milestones (2, 5, 6) against this same store.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

from .config import Engagement

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS engagement (
    id            TEXT PRIMARY KEY,
    target        TEXT NOT NULL,
    in_scope      TEXT NOT NULL,          -- JSON array
    out_of_scope  TEXT,                   -- JSON array
    mode          TEXT NOT NULL DEFAULT 'white',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset (
    id             INTEGER PRIMARY KEY,
    engagement_id  TEXT NOT NULL REFERENCES engagement(id),
    canonical_host TEXT NOT NULL,         -- unified IP<->hostname identity (Normalizer)
    kind           TEXT NOT NULL,         -- 'host' | 'service' | 'web_endpoint'
    port           INTEGER,
    url_path       TEXT,                  -- for web_endpoint only
    service        TEXT,                  -- scanner's guess: an ATTRIBUTE, not identity
    scope_status   TEXT NOT NULL,
    UNIQUE(engagement_id, canonical_host, kind, port, url_path)  -- service excluded on purpose
);

-- aliases map observed host strings (ip, hostname) -> canonical_host, so a machine seen two ways
-- is one asset (the mechanism behind idempotent re-run + no IP/hostname dupes).
CREATE TABLE IF NOT EXISTS host_alias (
    engagement_id  TEXT NOT NULL REFERENCES engagement(id),
    observed_host  TEXT NOT NULL,
    canonical_host TEXT NOT NULL,
    UNIQUE(engagement_id, observed_host)
);

CREATE TABLE IF NOT EXISTS finding (
    id            INTEGER PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagement(id),
    asset_id      INTEGER REFERENCES asset(id),
    kind          TEXT NOT NULL,
    product       TEXT, version TEXT, service TEXT, port INTEGER,
    detail        TEXT,                   -- JSON
    source_tool   TEXT NOT NULL,
    raw_ref       TEXT NOT NULL,
    confidence    REAL NOT NULL,
    observed_at   TEXT NOT NULL,
    UNIQUE(engagement_id, asset_id, kind, port)   -- service excluded -> reclassify updates, not dupes
);

CREATE TABLE IF NOT EXISTS interpretation (
    id            INTEGER PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagement(id),
    asset_id      INTEGER REFERENCES asset(id),
    summary       TEXT NOT NULL,
    cve_refs      TEXT,                   -- JSON array, model-asserted (validated before store)
    tech_notes    TEXT,
    model         TEXT NOT NULL,
    confidence    REAL,
    provenance    TEXT NOT NULL,          -- JSON: source finding ids
    source        TEXT NOT NULL DEFAULT 'model_asserted',   -- provenance class (quarantine-ready)
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    id            INTEGER PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagement(id),
    kind          TEXT NOT NULL,          -- 'tool' | 'query'
    detail        TEXT NOT NULL,          -- JSON: tool/outcome, or question/facts/reasoner/answer
    created_at    TEXT NOT NULL
);
"""

# Tables expected after init_schema (used by tests and the Checkpoint-0 probe).
EXPECTED_TABLES = frozenset(
    {"engagement", "asset", "host_alias", "finding", "interpretation", "run_log"}
)


class GraphStore:
    def __init__(self, path: str) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        try:
            con.execute("PRAGMA journal_mode = WAL")
            con.execute("PRAGMA foreign_keys = ON")
            con.row_factory = sqlite3.Row
            yield con
            con.commit()
        finally:
            con.close()

    def init_schema(self) -> None:
        with self.connect() as con:
            con.executescript(SCHEMA)

    def upsert_engagement(self, e: Engagement) -> None:
        """Insert the engagement row if absent; idempotent (re-run keeps one row, R5.3)."""
        import json

        with self.connect() as con:
            con.execute(
                """
                INSERT INTO engagement (id, target, in_scope, out_of_scope, mode, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    e.id,
                    e.target,
                    json.dumps(list(e.in_scope)),
                    json.dumps(list(e.out_of_scope)),
                    e.mode,
                    e.created_at,
                ),
            )

    def table_names(self) -> set[str]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        return {r["name"] for r in rows}

    def journal_mode(self) -> str:
        with self.connect() as con:
            return con.execute("PRAGMA journal_mode").fetchone()[0]
