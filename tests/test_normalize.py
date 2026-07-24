"""Milestone 2 — host canonicalization, normalization, dedup (Task 2.5, R3.3).

The slice-blocking case: a host seen as an IP by one tool and a hostname by another collapses to
ONE identity, and the scanner's service label is an attribute (a reclassifying re-scan updates,
not duplicates).
"""

from __future__ import annotations

from saltpilot.findings import Finding
from saltpilot.normalize import build_alias_map, canonicalize_host, dedup, normalize


def _finding(host, port, *, service="http", tool="nmap", confidence=0.9, raw_ref="r", detail=None):
    return Finding(
        engagement_id="e",
        asset_host=host,
        port=port,
        service=service,
        product=None,
        version=None,
        kind="service",
        detail=detail or {"protocol": "tcp"},
        source_tool=tool,
        raw_ref=raw_ref,
        confidence=confidence,
        scope_status="in_scope",
        observed_at="2026-07-24T00:00:00+00:00",
    )


def test_alias_map_unifies_hostname_and_ip():
    alias = build_alias_map({"lab.internal": ["10.10.10.7"]})
    assert alias["lab.internal"] == "10.10.10.7"
    assert alias["10.10.10.7"] == "10.10.10.7"


def test_canonicalize_ip_is_itself():
    assert canonicalize_host("10.10.10.7") == "10.10.10.7"


def test_canonicalize_hostname_via_alias():
    alias = {"lab.internal": "10.10.10.7"}
    assert canonicalize_host("lab.internal", alias_map=alias) == "10.10.10.7"


def test_canonicalize_hostname_via_resolver_fallback():
    assert canonicalize_host("lab.internal", resolver=lambda h: ["10.10.10.9"]) == "10.10.10.9"


def test_host_seen_as_ip_and_hostname_is_one_asset():
    alias = build_alias_map({"lab.internal": ["10.10.10.7"]})
    findings = [_finding("10.10.10.7", 80, tool="nmap"), _finding("lab.internal", 80, tool="httpx")]
    merged = dedup(normalize(findings, alias_map=alias))
    assert len(merged) == 1
    assert merged[0].asset_host == "10.10.10.7"
    # provenance from both tools is unioned
    tools = {p["tool"] for p in merged[0].detail["provenance"]}
    assert tools == {"nmap", "httpx"}


def test_service_reclassification_updates_not_duplicates():
    # Same (host, port), different service label between runs -> one finding, higher confidence wins.
    findings = [
        _finding("10.10.10.7", 8080, service="http-proxy", confidence=0.6),
        _finding("10.10.10.7", 8080, service="http", confidence=0.95),
    ]
    merged = dedup(findings)
    assert len(merged) == 1
    assert merged[0].service == "http"  # the higher-confidence classification


def test_distinct_ports_are_distinct_findings():
    findings = [_finding("10.10.10.7", 80), _finding("10.10.10.7", 443)]
    assert len(dedup(findings)) == 2
