"""Milestone 7.5 — the frozen held-out regression set (Copilot Section 13.5).

Re-run on every model or prompt change so a swap can't silently regress quality. Two parts:
  * grounded-answer spot-checks — deterministic, always run (guards the grounding invariant);
  * interpretation-quality eval — the objective Checkpoint-5 bar, runs only against a real model
    (set SALTPILOT_EVAL_MODEL_URL to an Ollama /v1 serving Foundation-Sec-8B, on the reference box).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from saltpilot.findings import Fact, Finding
from saltpilot.interpret import Interpreter, build_cve_validator
from saltpilot.query import ground_guard

EVAL = json.loads((Path(__file__).parent / "regression" / "eval_set.json").read_text())


# ---------------------------------------------------------- grounded-answer spot-checks (always)

@pytest.mark.parametrize("case", EVAL["grounded_answer_spotchecks"], ids=lambda c: c["name"])
def test_grounded_answer_regression(case):
    facts = [Fact(f["id"], f["kind"], f["text"], tuple(f["hosts"]), tuple(f["ports"]), tuple(f["cves"]))
             for f in case["facts"]]
    _, flagged = ground_guard(case["answer"], facts)
    assert flagged == sorted(case["expect_flagged"])


# ---------------------------------------------------------- interpretation quality (reference box)

@pytest.mark.skipif(not os.environ.get("SALTPILOT_EVAL_MODEL_URL"),
                    reason="set SALTPILOT_EVAL_MODEL_URL to a real Foundation-Sec-8B endpoint (reference box)")
def test_interpretation_quality_regression():
    from saltpilot.models import OllamaProvider

    spec = EVAL["interpretation_eval"]
    n, m, k = spec["thresholds"]["N"], spec["thresholds"]["M"], spec["thresholds"]["K"]
    findings = [
        Finding("eval", spec["host"], f["port"], f["service"], f["product"], f.get("version"),
                "service", {"protocol": "tcp"}, "nmap", f"eval#{f['port']}", 0.9, "in_scope", "t")
        for f in spec["findings"]
    ]
    model = OllamaProvider("foundation-sec-8b-reasoning", base_url=os.environ["SALTPILOT_EVAL_MODEL_URL"])
    interp = Interpreter().interpret(spec["host"], findings, model, build_cve_validator())

    blob = f"{interp.summary}\n{interp.tech_notes or ''}".lower()
    identified = sum(
        1 for f in spec["findings"]
        if str(f["service"]).lower() in blob or str(f.get("product", "")).lower() in blob
    )
    assert identified >= n, f"identified {identified}/{m} services, need >= {n}"

    if spec.get("expected_cves"):
        false_cves = [c for c in interp.cve_refs if c.upper() not in {e.upper() for e in spec["expected_cves"]}]
        assert len(false_cves) <= k, f"{len(false_cves)} false CVEs after validation ({false_cves}), allow <= {k}"
