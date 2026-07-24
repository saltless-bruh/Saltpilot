"""GraphStore — thin persistence over SQLite (WAL). Task 0.4 / Requirement 5.

The schema is the *minimal* graph the full typed node/edge model grows from. Provenance and a
`source` provenance-class live on `interpretation` from day one so the later write-back /
quarantine gate (Copilot Section 4.4) is a policy change, not a schema migration. All writes go
through this one path (single-writer discipline, R5.4).

v1 implements the schema + engagement upsert here; asset/finding/interpretation upserts and
`facts_for_query` land in their milestones (2, 5, 6) against this same store.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone

from .config import Engagement
from .findings import Asset, Finding


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

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

    # --------------------------------------------------------------- asset / finding upserts
    # NULL-safe matching: SQLite treats NULLs as distinct in a UNIQUE constraint, so idempotency
    # is enforced here with `col IS ?` (which matches NULL to NULL and value to value) rather than
    # relying on the table UNIQUE alone. Identity excludes the service label on purpose, so a
    # reclassifying re-scan updates the asset instead of duplicating it (R3.3, R5.3).
    @staticmethod
    def _upsert_asset(con: sqlite3.Connection, a: Asset) -> int:
        row = con.execute(
            "SELECT id FROM asset WHERE engagement_id = ? AND canonical_host = ? AND kind = ? "
            "AND port IS ? AND url_path IS ?",
            (a.engagement_id, a.canonical_host, a.kind, a.port, a.url_path),
        ).fetchone()
        if row is not None:
            con.execute(
                "UPDATE asset SET service = COALESCE(?, service), scope_status = ? WHERE id = ?",
                (a.service, a.scope_status, row["id"]),
            )
            return row["id"]
        cur = con.execute(
            "INSERT INTO asset (engagement_id, canonical_host, kind, port, url_path, service, scope_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (a.engagement_id, a.canonical_host, a.kind, a.port, a.url_path, a.service, a.scope_status),
        )
        return cur.lastrowid

    @staticmethod
    def _upsert_finding(con: sqlite3.Connection, f: Finding, asset_id: int | None) -> int:
        detail_json = json.dumps(f.detail, default=str)
        row = con.execute(
            "SELECT id FROM finding WHERE engagement_id = ? AND asset_id IS ? AND kind = ? AND port IS ?",
            (f.engagement_id, asset_id, f.kind, f.port),
        ).fetchone()
        if row is not None:
            con.execute(
                "UPDATE finding SET product = ?, version = ?, service = ?, detail = ?, source_tool = ?, "
                "raw_ref = ?, confidence = ?, observed_at = ? WHERE id = ?",
                (f.product, f.version, f.service, detail_json, f.source_tool, f.raw_ref,
                 f.confidence, f.observed_at, row["id"]),
            )
            return row["id"]
        cur = con.execute(
            "INSERT INTO finding (engagement_id, asset_id, kind, product, version, service, port, "
            "detail, source_tool, raw_ref, confidence, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f.engagement_id, asset_id, f.kind, f.product, f.version, f.service, f.port,
             detail_json, f.source_tool, f.raw_ref, f.confidence, f.observed_at),
        )
        return cur.lastrowid

    def upsert_asset(self, a: Asset) -> int:
        with self.connect() as con:
            return self._upsert_asset(con, a)

    def upsert_finding(self, f: Finding, asset_id: int | None = None) -> int:
        with self.connect() as con:
            return self._upsert_finding(con, f, asset_id)

    def persist_findings(self, engagement: Engagement, findings: Iterator[Finding]) -> dict:
        """Persist findings as assets + findings in one writer transaction. Idempotent.

        Each finding materializes a `host` asset plus (for services/web endpoints) a finer asset it
        attaches to. Re-running the same recon updates rows in place — no duplicates (Checkpoint 2).
        """
        self.upsert_engagement(engagement)  # ensure the FK target row exists
        touched_assets: set[int] = set()
        n_findings = 0
        with self.connect() as con:
            for f in findings:
                host_id = self._upsert_asset(con, Asset(f.engagement_id, f.asset_host, "host"))
                touched_assets.add(host_id)
                if f.kind == "service" and f.port is not None:
                    target_id = self._upsert_asset(
                        con, Asset(f.engagement_id, f.asset_host, "service", port=f.port, service=f.service)
                    )
                elif f.kind == "web_endpoint":
                    target_id = self._upsert_asset(
                        con,
                        Asset(
                            f.engagement_id, f.asset_host, "web_endpoint",
                            port=f.port, url_path=f.detail.get("url_path"), service=f.service,
                        ),
                    )
                else:
                    target_id = host_id
                touched_assets.add(target_id)
                self._upsert_finding(con, f, target_id)
                n_findings += 1
        return {"assets": len(touched_assets), "findings": n_findings}

    def log_run(self, engagement_id: str, kind: str, detail: dict) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO run_log (engagement_id, kind, detail, created_at) VALUES (?, ?, ?, ?)",
                (engagement_id, kind, json.dumps(detail, default=str), _utcnow_iso()),
            )
