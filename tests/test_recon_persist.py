"""Milestone 2 — the recon runner + persistence, driven by a fixture (Tasks 2.4, 2.6, 2.7).

Hermetic: a fake executor replays the real nmap fixture, so this exercises the whole
runner -> normalize -> dedup -> persist path with no nmap binary. Asserts findings persist and a
second run adds no duplicates (Checkpoint 2's idempotency claim).
"""

from __future__ import annotations

from pathlib import Path

from saltpilot.adapters.nmap import NmapAdapter
from saltpilot.recon import build_network_recon
from saltpilot.store import GraphStore
from saltpilot.workbench import RawOutput, ReconOutcome, ToolStatus

FIXTURE = (Path(__file__).parent / "fixtures" / "nmap_localhost.xml").read_text()


def _counts(store: GraphStore) -> tuple[int, int]:
    with store.connect() as con:
        assets = con.execute("SELECT count(*) FROM asset").fetchone()[0]
        findings = con.execute("SELECT count(*) FROM finding").fetchone()[0]
    return assets, findings


def _runner(make_engagement, tmp_path, monkeypatch):
    # Stub availability so the test needs no nmap binary; fake executor replays the fixture.
    monkeypatch.setattr(NmapAdapter, "is_available", lambda self: ToolStatus("nmap", True, version="7.94"))

    def fake_executor(inv, timeout_secs):
        return RawOutput.of(FIXTURE), ReconOutcome.OK

    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "engagement.sqlite"))
    store.init_schema()
    return build_network_recon(eng, store, executor=fake_executor), store


def test_recon_persists_services(make_engagement, tmp_path, monkeypatch):
    runner, store = _runner(make_engagement, tmp_path, monkeypatch)
    result = runner.run()

    assert {f.port for f in result.findings} == {8000, 9001}
    assert result.coverage_summary().get("ok") == 1
    assert _counts(store) == (3, 2)  # 1 host asset + 2 service assets; 2 findings


def test_recon_is_idempotent(make_engagement, tmp_path, monkeypatch):
    runner, store = _runner(make_engagement, tmp_path, monkeypatch)
    runner.run()
    before = _counts(store)
    runner.run()  # a second identical run must not duplicate
    after = _counts(store)
    assert before == after == (3, 2)


def test_out_of_scope_target_is_skipped_not_scanned(make_engagement, tmp_path, monkeypatch):
    # Target resolves to nothing in scope -> SKIPPED coverage, no findings, no crash.
    monkeypatch.setattr(NmapAdapter, "is_available", lambda self: ToolStatus("nmap", True))
    eng = make_engagement(tmp_path, target="8.8.8.8", in_scope=("10.0.0.0/24",))
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()

    def fake_executor(inv, timeout_secs):  # should never be called
        raise AssertionError("executor ran on an out-of-scope target")

    result = build_network_recon(eng, store, executor=fake_executor).run()
    assert result.findings == []
    assert result.coverage_summary().get("skipped") == 1
