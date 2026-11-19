"""Milestone 3 — the two-stage (nmap -> httpx) pipeline and the feed-all-ports fix (Tasks 3.3, 3.4).

Hermetic: a fake executor replays the real nmap and httpx fixtures, so the whole tool-feeds-tool
path is exercised with no binaries. Plus a direct test of the slice-blocking httpx/nmap fix.
"""

from __future__ import annotations

from pathlib import Path

from saltpilot.adapters.httpx import HttpxAdapter
from saltpilot.adapters.nmap import NmapAdapter
from saltpilot.findings import Finding
from saltpilot.recon import build_recon, web_feed
from saltpilot.store import GraphStore
from saltpilot.workbench import RawOutput, ReconOutcome, ToolStatus

FIX = Path(__file__).parent / "fixtures"
NMAP = (FIX / "nmap_localhost.xml").read_text()
HTTPX = (FIX / "httpx_localhost.jsonl").read_text()


def _svc(host: str, port: int, service: str) -> Finding:
    return Finding("e", host, port, service, None, None, "service", {"protocol": "tcp"},
                   "nmap", "r", 0.9, "in_scope", "t")


def _counts(store: GraphStore) -> tuple[int, int]:
    with store.connect() as con:
        assets = con.execute("SELECT count(*) FROM asset").fetchone()[0]
        findings = con.execute("SELECT count(*) FROM finding").fetchone()[0]
    return assets, findings


def test_web_feed_includes_all_open_ports_not_just_http():
    # The slice-blocking fix: a non-http-labeled open port must still be fed to httpx.
    findings = [_svc("10.10.10.7", 22, "ssh"), _svc("10.10.10.7", 80, "http"), _svc("10.10.10.7", 8443, "ssl/unknown")]
    assert web_feed(findings) == {"10.10.10.7": ["22", "80", "8443"]}


def test_two_stage_pipeline_persists_network_and_web(make_engagement, tmp_path, monkeypatch):
    monkeypatch.setattr(NmapAdapter, "is_available", lambda self: ToolStatus("nmap", True))
    monkeypatch.setattr(HttpxAdapter, "is_available", lambda self: ToolStatus("httpx", True))

    def fake_executor(inv, timeout_secs):
        if inv.tool == "nmap":
            return RawOutput.of(NMAP), ReconOutcome.OK
        if inv.tool == "httpx":
            assert inv.stdin and "127.0.0.1:8000" in inv.stdin  # fed from nmap's open ports
            return RawOutput.of(HTTPX), ReconOutcome.OK
        raise AssertionError(inv.tool)

    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    result = build_recon(eng, store, executor=fake_executor).run()

    assert sum(1 for f in result.findings if f.kind == "service") == 2
    assert sum(1 for f in result.findings if f.kind == "web_endpoint") == 2
    assert result.coverage_summary().get("ok") == 2  # nmap + httpx
    # 1 host + 2 service + 2 web_endpoint assets; 4 findings
    assert _counts(store) == (5, 4)


def test_two_stage_pipeline_is_idempotent(make_engagement, tmp_path, monkeypatch):
    monkeypatch.setattr(NmapAdapter, "is_available", lambda self: ToolStatus("nmap", True))
    monkeypatch.setattr(HttpxAdapter, "is_available", lambda self: ToolStatus("httpx", True))

    def fake_executor(inv, timeout_secs):
        return (RawOutput.of(NMAP) if inv.tool == "nmap" else RawOutput.of(HTTPX)), ReconOutcome.OK

    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    build_recon(eng, store, executor=fake_executor).run()
    before = _counts(store)
    build_recon(eng, store, executor=fake_executor).run()
    assert _counts(store) == before == (5, 4)


def test_missing_httpx_degrades_to_capability_gap(make_engagement, tmp_path, monkeypatch):
    # httpx unavailable -> web stage records a capability gap, network findings still persist (R2.3).
    monkeypatch.setattr(NmapAdapter, "is_available", lambda self: ToolStatus("nmap", True))
    monkeypatch.setattr(HttpxAdapter, "is_available",
                        lambda self: ToolStatus("httpx", False, detail="not installed"))

    def fake_executor(inv, timeout_secs):
        assert inv.tool == "nmap"  # httpx never runs when unavailable
        return RawOutput.of(NMAP), ReconOutcome.OK

    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    result = build_recon(eng, store, executor=fake_executor).run()

    assert sum(1 for f in result.findings if f.kind == "web_endpoint") == 0
    assert sum(1 for f in result.findings if f.kind == "service") == 2
    assert result.coverage_summary().get("permanent") == 1  # the capability gap
