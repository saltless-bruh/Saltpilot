"""Milestone 6 — retrieval, grounding prompt, and CopilotQuery (Tasks 6.1-6.4; R6.1-6.5, R8.2)."""

from __future__ import annotations

from saltpilot.findings import Finding
from saltpilot.interpret import Interpretation
from saltpilot.models import Completion, ProviderUnavailable, Role
from saltpilot.query import CopilotQuery, grounding_prompt
from saltpilot.store import GraphStore


class FakeReasoner:
    def __init__(self, text="", exc=None, provider="ollama", model="qwen3-4b-thinking-2507", fell_back=False):
        self.text, self.exc, self.provider, self.model, self.fell_back = text, exc, provider, model, fell_back
        self.calls = []

    def complete(self, role, prompt, *, max_tokens=1024, system=None):
        self.calls.append(role)
        if self.exc:
            raise self.exc
        return Completion(self.text, self.model, self.provider, role, fell_back=self.fell_back)


def _seed(tmp_path, make_engagement):
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    store.persist_findings(eng, [
        Finding(eng.id, "10.10.10.7", 8899, "http", "nginx", "1.25", "service", {"protocol": "tcp"},
                "nmap", "r#1", 0.9, "in_scope", "t"),
    ])
    store.upsert_interpretation(
        Interpretation(eng.id, "10.10.10.7", "an nginx host", ["CVE-2014-0160"], "n",
                       "foundation-sec-8b-reasoning", 0.5, ["r#1"]))
    return eng, store


# ---------------------------------------------------------- retrieval (6.1)

def test_broad_question_returns_all_facts(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    facts = store.facts_for_query(eng.id, "what is the most interesting thing you found?")
    kinds = {f.kind for f in facts}
    assert kinds == {"asset", "finding", "interpretation"}  # host+service assets, finding, interp


def test_specific_keyword_filters(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    got = store.facts_for_query(eng.id, "tell me about port 8899")
    assert got and all("8899" in f.text for f in got)


def test_question_matching_nothing_returns_empty(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    assert store.facts_for_query(eng.id, "anything about mongodb?") == []


def test_validated_cve_is_retrievable(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    facts = store.facts_for_query(eng.id, "CVE-2014-0160")
    assert any("CVE-2014-0160" in f.cves for f in facts)


# ---------------------------------------------------------- grounding prompt (6.2)

def test_grounding_prompt_carries_facts_and_instruction(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    facts = store.facts_for_query(eng.id, None)
    system, user = grounding_prompt("what did you find?", facts)
    assert "only" in system.lower() and "no relevant facts found" in system.lower()
    assert "[finding:" in user and "QUESTION: what did you find?" in user


# ---------------------------------------------------------- CopilotQuery.answer (6.2-6.5, R8.2)

def test_answer_is_grounded_and_cites_facts(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    model = FakeReasoner(text="Host 10.10.10.7 runs nginx on port 8899, likely CVE-2014-0160.")
    ans = CopilotQuery(store, eng.id).answer("summarize the surface", model)
    assert ans.flagged == []
    assert ans.grounded                          # cited facts by entity/id
    assert ans.reasoner == "ollama/qwen3-4b-thinking-2507"
    assert model.calls == [Role.REASONING]


def test_answer_guard_strips_invented_entities(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    model = FakeReasoner(text="Also 10.9.9.9 has CVE-2021-99999 on port 3306.")
    ans = CopilotQuery(store, eng.id).answer("summarize the surface", model)
    assert set(ans.flagged) == {"10.9.9.9", "CVE-2021-99999", "3306"}
    assert "[unverified: 10.9.9.9]" in ans.text


def test_no_relevant_facts_does_not_call_model(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    model = FakeReasoner(text="should never be used")
    ans = CopilotQuery(store, eng.id).answer("tell me about mongodb", model)
    assert ans.no_facts is True
    assert ans.text == "No relevant facts found."
    assert ans.reasoner == "none"
    assert model.calls == []                     # honest, no invention (R6.4)


def test_reasoner_unavailable_degrades(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    model = FakeReasoner(exc=ProviderUnavailable("both cloud and local down"))
    ans = CopilotQuery(store, eng.id).answer("summarize the surface", model)
    assert ans.reasoner == "unavailable" and "unavailable" in ans.text.lower()


def test_answer_reports_cloud_fallback(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    model = FakeReasoner(text="nginx on 10.10.10.7:8899", provider="ollama", fell_back=True)
    ans = CopilotQuery(store, eng.id).answer("summarize the surface", model)
    assert ans.fell_back is True                 # R6.3: operator can see the fallback


def test_query_is_logged(tmp_path, make_engagement):
    eng, store = _seed(tmp_path, make_engagement)
    CopilotQuery(store, eng.id).answer("summarize the surface", FakeReasoner(text="nginx on port 8899"))
    with store.connect() as con:
        rows = con.execute("SELECT detail FROM run_log WHERE kind = 'query'").fetchall()
    assert len(rows) == 1 and "reasoner" in rows[0]["detail"]  # R8.2
