"""Milestone 3 — the httpx parser against a real captured `httpx -json` fixture (Task 3.2, R2.2)."""

from __future__ import annotations

import json
from pathlib import Path

from saltpilot.adapters.httpx import HttpxAdapter
from saltpilot.workbench import RawOutput, ToolInvocation

FIXTURES = Path(__file__).parent / "fixtures"


def _raw(name: str) -> RawOutput:
    return RawOutput.of((FIXTURES / name).read_text())


def _invocation(engagement_id: str = "test-eng") -> ToolInvocation:
    return ToolInvocation(
        tool="httpx",
        argv=("httpx", "-json", "-silent"),
        intent="probe_web",
        engagement_id=engagement_id,
        gated_ips=("127.0.0.1",),
        output_format="httpx-json",
        stdin="127.0.0.1:8000\n127.0.0.1:9001\n",
    )


def test_parses_web_endpoints_from_real_capture():
    raw = _raw("httpx_localhost.jsonl")
    records = {int(json.loads(l)["port"]): json.loads(l) for l in raw.stdout.splitlines() if l.strip()}
    findings = sorted(HttpxAdapter().parse(_invocation(), raw), key=lambda f: f.port)

    assert {f.port for f in findings} == {8000, 9001}
    for f in findings:
        r = records[f.port]
        assert f.engagement_id == "test-eng"
        assert f.asset_host == "127.0.0.1"
        assert f.kind == "web_endpoint"
        assert f.service == "http"
        assert f.product == r["webserver"]
        assert f.version is None
        assert f.detail["status_code"] == r["status_code"]
        assert f.detail["title"] == r["title"]
        assert f.detail["tech"] == r["tech"]
        assert f.detail["url"] == r["url"]
        assert f.detail["url_path"] == r["path"]
        assert f.detail["scheme"] == "http"
        assert f.observed_at == r["timestamp"]
        assert f.raw_ref == f"{raw.ref}#127.0.0.1:{f.port}{r['path']}"
        assert f.source_tool == "httpx"
        assert f.confidence == 0.9


def test_failed_and_malformed_lines_are_skipped():
    good = (
        '{"host":"10.0.0.5","port":"80","scheme":"http","path":"/","status_code":200,'
        '"title":"ok","webserver":"nginx","tech":["Nginx"],"timestamp":"2026-07-24T00:00:00Z"}'
    )
    failed = '{"host":"10.0.0.5","port":"81","failed":true}'
    garbage = "not json at all {{{"
    raw = RawOutput.of("\n".join([good, failed, garbage, ""]))
    findings = HttpxAdapter().parse(_invocation(), raw)
    assert len(findings) == 1
    assert (findings[0].port, findings[0].kind, findings[0].product) == (80, "web_endpoint", "nginx")


def test_https_carries_tls_detail():
    rec = (
        '{"host":"10.0.0.5","port":"443","scheme":"https","path":"/","status_code":200,'
        '"tls":{"subject_cn":"lab"},"timestamp":"2026-07-24T00:00:00Z"}'
    )
    findings = HttpxAdapter().parse(_invocation(), RawOutput.of(rec))
    assert findings[0].service == "https"
    assert findings[0].detail["tls"] == {"subject_cn": "lab"}
