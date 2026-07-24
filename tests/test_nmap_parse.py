"""Milestone 2 — the nmap parser, the highest-value correctness test (Task 2.3, R3).

Parsers are where correctness lives, so test them hardest: assert the EXACT Finding list from a
real captured `nmap -sV -oX` fixture, and assert graceful partial parse on a truncated one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from saltpilot.adapters.nmap import NmapAdapter
from saltpilot.findings import Finding
from saltpilot.workbench import RawOutput, ToolInvocation

FIXTURES = Path(__file__).parent / "fixtures"


def _raw(name: str) -> RawOutput:
    return RawOutput.of((FIXTURES / name).read_text())


def _invocation(engagement_id: str = "test-eng") -> ToolInvocation:
    return ToolInvocation(
        tool="nmap",
        argv=("nmap", "-sV", "-oX", "-", "127.0.0.1"),
        intent="discover_services",
        engagement_id=engagement_id,
        gated_ips=("127.0.0.1",),
        output_format="nmap-xml",
    )


def test_parses_exact_findings_from_real_capture():
    raw = _raw("nmap_localhost.xml")
    inv = _invocation()
    findings = NmapAdapter().parse(inv, raw)

    observed_at = datetime.fromtimestamp(1784865530, tz=timezone.utc).isoformat()
    expected = [
        Finding(
            engagement_id="test-eng",
            asset_host="127.0.0.1",
            port=port,
            service="http",
            product="SimpleHTTPServer",
            version="0.6",
            kind="service",
            detail={
                "protocol": "tcp",
                "state": "open",
                "method": "probed",
                "extrainfo": "Python 3.11.15",
                "cpe": ["cpe:/a:python:simplehttpserver:0.6"],
                "hostnames": ["localhost"],
            },
            source_tool="nmap",
            raw_ref=f"{raw.ref}#127.0.0.1:{port}",
            confidence=1.0,
            scope_status="in_scope",
            observed_at=observed_at,
        )
        for port in (8000, 9001)
    ]
    assert findings == expected


def test_closed_ports_do_not_become_findings():
    # The fixture has 22 and 80 closed; only the two open ports may surface.
    findings = NmapAdapter().parse(_invocation(), _raw("nmap_localhost.xml"))
    assert {f.port for f in findings} == {8000, 9001}


def test_engagement_id_is_stamped_from_invocation():
    findings = NmapAdapter().parse(_invocation("eng-42"), _raw("nmap_localhost.xml"))
    assert all(f.engagement_id == "eng-42" for f in findings)


def test_truncated_output_salvages_complete_hosts_without_crashing():
    # Host A (10.10.10.7) is complete; host B is cut off mid-element. We must salvage A, not crash.
    findings = NmapAdapter().parse(_invocation(), _raw("nmap_truncated.xml"))
    assert len(findings) == 1
    f = findings[0]
    assert (f.asset_host, f.port, f.service, f.product, f.version) == (
        "10.10.10.7",
        22,
        "ssh",
        "OpenSSH",
        "8.9p1",
    )


def test_totally_unparseable_output_returns_empty_not_crash():
    findings = NmapAdapter().parse(_invocation(), RawOutput.of("this is not xml at all <<<"))
    assert findings == []
