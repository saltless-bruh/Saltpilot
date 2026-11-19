"""Milestone 5 — persistence of interpretations + wiring into the recon flow (Task 5.3)."""

from __future__ import annotations

import json
from pathlib import Path

from saltpilot.adapters.httpx import HttpxAdapter
from saltpilot.adapters.nmap import NmapAdapter
from saltpilot.interpret import Interpretation, build_cve_validator
from saltpilot.models import Completion, ProviderUnavailable, Role
from saltpilot.recon import build_recon
from saltpilot.store import GraphStore
from saltpilot.workbench import RawOutput, ReconOutcome, ToolStatus

FIX = Path(__file__).parent / "fixtures"
NMAP = (FIX / "nmap_localhost.xml").read_text()
HTTPX = (FIX / "httpx_localhost.jsonl").read_text()
SEED = str(FIX / "cve_seed.json")


class FakeModel:
    def __init__(self, reply="", exc=None, model="foundation-sec-8b-reasoning"):
        self.reply, self.exc, self.model = reply, exc, model

    def complete(self, role, prompt, *, max_tokens=1024, system=None):
        if self.exc:
            raise self.exc
        return Completion(text=self.reply, model=self.model, provider="ollama", role=role)


def _interp_rows(store):
    with store.connect() as con:
        return con.execute("SELECT id, summary, cve_refs, source, model FROM interpretation").fetchall()


# ---------------------------------------------------------- store persistence

def test_upsert_interpretation_is_idempotent_and_updates(make_engagement, tmp_path):
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    store.upsert_engagement(eng)

    interp = Interpretation(eng.id, "10.10.10.7", "first", ["CVE-2014-0160"], "n",
                            "foundation-sec-8b-reasoning", 0.5, ["r1"])
    id1 = store.upsert_interpretation(interp)
    rows = _interp_rows(store)
    assert len(rows) == 1
    assert json.loads(rows[0]["cve_refs"]) == ["CVE-2014-0160"]
    assert rows[0]["source"] == "model_asserted"

    interp.summary = "second"
    id2 = store.upsert_interpretation(interp)   # same host -> update, not a new row
    rows = _interp_rows(store)
    assert id1 == id2 and len(rows) == 1 and rows[0]["summary"] == "second"


# ---------------------------------------------------------- recon flow wiring

def _fake_exec(inv, timeout_secs):
    return (RawOutput.of(NMAP) if inv.tool == "nmap" else RawOutput.of(HTTPX)), ReconOutcome.OK


def _tools_available(monkeypatch):
    monkeypatch.setattr(NmapAdapter, "is_available", lambda self: ToolStatus("nmap", True))
    monkeypatch.setattr(HttpxAdapter, "is_available", lambda self: ToolStatus("httpx", True))


def test_recon_flow_interprets_and_persists(make_engagement, tmp_path, monkeypatch):
    _tools_available(monkeypatch)
    model = FakeModel(reply=json.dumps({"summary": "web host", "cves": [{"id": "CVE-2014-0160", "product": "OpenSSL"}]}))
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()

    result = build_recon(eng, store, executor=_fake_exec, model=model, cves=build_cve_validator(SEED)).run()

    assert result.interpretations == 1           # one host (127.0.0.1)
    rows = _interp_rows(store)
    assert len(rows) == 1
    assert json.loads(rows[0]["cve_refs"]) == ["CVE-2014-0160"]  # validator-approved only


def test_recon_flow_without_model_skips_interpretation(make_engagement, tmp_path, monkeypatch):
    _tools_available(monkeypatch)
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    result = build_recon(eng, store, executor=_fake_exec).run()   # no model -> no interpretation
    assert result.interpretations == 0
    assert _interp_rows(store) == []
    assert len(result.findings) > 0                                # recon still worked


def test_recon_flow_degrades_when_model_unavailable(make_engagement, tmp_path, monkeypatch):
    _tools_available(monkeypatch)
    model = FakeModel(exc=ProviderUnavailable("local model down"))
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()

    result = build_recon(eng, store, executor=_fake_exec, model=model, cves=build_cve_validator(SEED)).run()

    assert result.interpretations == 0            # interpret failed, recorded
    assert _interp_rows(store) == []
    with store.connect() as con:                  # findings persisted regardless (degrade, not fail)
        assert con.execute("SELECT count(*) FROM finding").fetchone()[0] > 0
