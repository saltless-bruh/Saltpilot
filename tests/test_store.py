"""Milestone 0 — the graph store schema + engagement upsert (Task 0.4, R5)."""

from __future__ import annotations

from saltpilot.config import load_engagement
from saltpilot.store import EXPECTED_TABLES, GraphStore

import textwrap

CFG = """
[engagement]
target = "lab.internal"
in_scope = ["10.10.10.0/24"]
out_of_scope = ["10.10.10.1"]
mode = "white"
kind = "practice"

[models]
analysis = "foundation-sec-8b-reasoning"
reasoner_cloud = "deepseek-v4-flash"
reasoner_local = "qwen3-4b-thinking-2507"
cve_source = "nvd_local"

[recon]
tool_timeout_secs = 300
nmap_args = "-sV -T4"
"""


def _store(tmp_path) -> GraphStore:
    return GraphStore(str(tmp_path / "engagement.sqlite"))


def test_init_schema_creates_all_tables(tmp_path):
    s = _store(tmp_path)
    s.init_schema()
    assert EXPECTED_TABLES.issubset(s.table_names())


def test_wal_mode_enabled(tmp_path):
    s = _store(tmp_path)
    s.init_schema()
    assert s.journal_mode().lower() == "wal"


def test_engagement_upsert_is_idempotent(tmp_path):
    p = tmp_path / "engagement.toml"
    p.write_text(textwrap.dedent(CFG))
    e = load_engagement(str(p))

    s = _store(tmp_path)
    s.init_schema()
    s.upsert_engagement(e)
    s.upsert_engagement(e)  # re-run must not duplicate

    with s.connect() as con:
        rows = con.execute("SELECT id FROM engagement WHERE id = ?", (e.id,)).fetchall()
    assert len(rows) == 1


def test_schema_survives_reopen(tmp_path):
    # Restart resilience: a fresh GraphStore over the same file sees the persisted schema.
    path = str(tmp_path / "persist.sqlite")
    GraphStore(path).init_schema()
    assert EXPECTED_TABLES.issubset(GraphStore(path).table_names())
