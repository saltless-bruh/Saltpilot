"""Milestone 7 — end-to-end: engage -> recon -> interpret -> ask, and honest degrade (7.1, 7.2).

Hermetic: real captured fixtures replayed through a fake executor, a fake analysis model for
interpretation, and a fake reasoner for the answer — so the whole core loop runs with no binaries,
models, or network, while the deterministic spine (parse, normalize, validate, guard) is real.
"""

from __future__ import annotations

import json
from pathlib import Path

from saltpilot.adapters.httpx import HttpxAdapter
from saltpilot.adapters.nmap import NmapAdapter
from saltpilot.interpret import build_cve_validator
from saltpilot.models import Completion, ProviderUnavailable, Role
from saltpilot.query import CopilotQuery
from saltpilot.recon import build_recon
from saltpilot.store import GraphStore
from saltpilot.workbench import RawOutput, ReconOutcome, ToolStatus

FIX = Path(__file__).parent / "fixtures"
NMAP = (FIX / "nmap_localhost.xml").read_text()
HTTPX = (FIX / "httpx_localhost.jsonl").read_text()
SEED = str(FIX / "cve_seed.json")


class FakeModel:
    def __init__(self, reply="", exc=None, model="foundation-sec-8b-reasoning", provider="ollama", fell_back=False):
        self.reply, self.exc, self.model, self.provider, self.fell_back = reply, exc, model, provider, fell_back

    def complete(self, role, prompt, *, max_tokens=1024, system=None):
        if self.exc:
            raise self.exc
        return Completion(self.reply, self.model, self.provider, role, fell_back=self.fell_back)


def _tools_available(monkeypatch):
    monkeypatch.setattr(NmapAdapter, "is_available", lambda self: ToolStatus("nmap", True))
    monkeypatch.setattr(HttpxAdapter, "is_available", lambda self: ToolStatus("httpx", True))


def _counts(store):
    with store.connect() as con:
        return (con.execute("SELECT count(*) FROM finding").fetchone()[0],
                con.execute("SELECT count(*) FROM interpretation").fetchone()[0])


# ---------------------------------------------------------- 7.1 full loop from a clean DB

def test_full_loop_engage_recon_interpret_ask(make_engagement, tmp_path, monkeypatch):
    _tools_available(monkeypatch)

    def executor(inv, timeout_secs):
        return (RawOutput.of(NMAP) if inv.tool == "nmap" else RawOutput.of(HTTPX)), ReconOutcome.OK

    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "engagement.sqlite"))   # clean DB
    store.init_schema()

    analysis = FakeModel(reply=json.dumps({"summary": "web host", "cves": [{"id": "CVE-2014-0160", "product": "OpenSSL"}]}))
    result = build_recon(eng, store, executor=executor, model=analysis, cves=build_cve_validator(SEED)).run()

    findings, interps = _counts(store)
    assert findings > 0 and interps == 1                       # recon + interpret populated the graph

    reasoner = FakeModel(reply="The host 127.0.0.1 exposes http on port 8000 [finding:1]; see CVE-2014-0160 [interp:1].")
    ans = CopilotQuery(store, eng.id).answer("what's the most interesting thing you found?", reasoner)

    assert ans.no_facts is False
    assert ans.flagged == []                                   # nothing invented
    assert ans.grounded                                        # traceable to stored facts
    assert ans.reasoner == "ollama/foundation-sec-8b-reasoning"


# ---------------------------------------------------------- 7.2 degrade, record, still answer

def test_degrade_on_tool_failure_still_persists_and_answers(make_engagement, tmp_path, monkeypatch):
    _tools_available(monkeypatch)

    def executor(inv, timeout_secs):
        if inv.tool == "nmap":
            return RawOutput.of(NMAP), ReconOutcome.OK
        return RawOutput.of("", stderr="httpx crashed"), ReconOutcome.PERMANENT   # tool dies mid-run

    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    result = build_recon(eng, store, executor=executor).run()

    # degrade coverage, never correctness (R2.5, R8.3): nmap findings persisted, httpx failure recorded
    assert any(f.kind == "service" for f in result.findings)
    assert all(f.kind != "web_endpoint" for f in result.findings)
    assert result.coverage_summary().get("permanent", 0) >= 1

    # the copilot still answers over the partial results
    reasoner = FakeModel(reply="127.0.0.1 has http on port 8000 [finding:1].")
    ans = CopilotQuery(store, eng.id).answer("what did you find?", reasoner)
    assert ans.no_facts is False and ans.flagged == []


def test_interpretation_failure_does_not_break_the_loop(make_engagement, tmp_path, monkeypatch):
    _tools_available(monkeypatch)

    def executor(inv, timeout_secs):
        return (RawOutput.of(NMAP) if inv.tool == "nmap" else RawOutput.of(HTTPX)), ReconOutcome.OK

    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    # analysis model down: findings still persist, interpretation count 0, ask still works
    result = build_recon(eng, store, executor=executor,
                         model=FakeModel(exc=ProviderUnavailable("down")), cves=build_cve_validator(SEED)).run()
    findings, interps = _counts(store)
    assert findings > 0 and interps == 0
    ans = CopilotQuery(store, eng.id).answer("what did you find?", FakeModel(reply="127.0.0.1 http on port 8000"))
    assert ans.no_facts is False
