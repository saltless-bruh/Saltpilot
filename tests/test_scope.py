"""Milestone 1 / Checkpoint 1 — the fail-closed scope gate (Requirement 1).

Covers Task 1.3: in-scope host, out-of-scope host, in-CIDR, explicit out-of-scope override,
malformed input, resolver error -> fail closed; PLUS the slice-blocking cases: resolve_and_gate
returns IPs (never hostnames), and a hostname resolving to an out-of-scope IP is rejected.
"""

from __future__ import annotations

import ipaddress
import socket

import pytest

from saltpilot.scope import ScopeGate, ScopeVerdict


def make_resolver(mapping: dict[str, list[str]], errors: tuple[str, ...] = ()):
    def _resolve(host: str) -> list[str]:
        if host in errors:
            raise socket.gaierror("simulated resolver failure")
        return mapping.get(host, [])

    return _resolve


# --------------------------------------------------------------------------- check()

@pytest.fixture
def gate() -> ScopeGate:
    return ScopeGate(
        in_scope=["*.acme.com", "lab.internal", "10.10.10.0/24"],
        out_of_scope=["blog.acme.com", "10.10.10.1"],
    )


def test_in_scope_wildcard_subdomain(gate):
    assert gate.check("admin.acme.com") is ScopeVerdict.IN_SCOPE


def test_in_scope_exact_domain(gate):
    assert gate.check("lab.internal") is ScopeVerdict.IN_SCOPE


def test_wildcard_does_not_match_apex(gate):
    # '*.acme.com' authorizes subdomains only; the apex is not in scope.
    assert gate.check("acme.com") is ScopeVerdict.OUT_OF_SCOPE


def test_out_of_scope_unknown_domain(gate):
    assert gate.check("evil.example.org") is ScopeVerdict.OUT_OF_SCOPE


def test_explicit_domain_exclusion_is_skip(gate):
    # blog.acme.com matches the in-scope wildcard but is explicitly excluded -> SKIP wins.
    assert gate.check("blog.acme.com") is ScopeVerdict.SKIP


def test_ip_in_cidr(gate):
    assert gate.check("10.10.10.5") is ScopeVerdict.IN_SCOPE


def test_ip_explicit_exclusion_wins_over_cidr(gate):
    assert gate.check("10.10.10.1") is ScopeVerdict.SKIP


def test_ip_outside_scope(gate):
    assert gate.check("8.8.8.8") is ScopeVerdict.OUT_OF_SCOPE


@pytest.mark.parametrize("bad", ["", "   ", None, "not a token !!", "999.999.999.999"])
def test_malformed_or_ambiguous_fails_closed(gate, bad):
    assert gate.check(bad) is ScopeVerdict.OUT_OF_SCOPE


# ------------------------------------------------------------------- resolve_and_gate()

def test_resolve_and_gate_returns_in_scope_ip():
    gate = ScopeGate(
        in_scope=["10.10.10.0/24"],
        out_of_scope=["10.10.10.1"],
        resolver=make_resolver({"host1.lab": ["10.10.10.5"]}),
    )
    result = gate.resolve_and_gate("host1.lab")
    assert result == ["10.10.10.5"]
    # It must hand tools IPs, never the hostname.
    assert all(_is_ip(x) for x in result)
    assert "host1.lab" not in result


def test_hostname_resolving_to_out_of_scope_ip_is_rejected():
    # The gate-bypass fix: name is not explicitly denied, but its resolved IP is excluded.
    gate = ScopeGate(
        in_scope=["10.10.10.0/24"],
        out_of_scope=["10.10.10.1"],
        resolver=make_resolver({"gw.lab": ["10.10.10.1"]}),
    )
    assert gate.resolve_and_gate("gw.lab") == []


def test_hostname_resolving_outside_declared_cidr_is_rejected():
    # CIDRs are declared -> a name that resolves outside them is dropped (declared ranges bound it).
    gate = ScopeGate(
        in_scope=["10.10.10.0/24"],
        out_of_scope=[],
        resolver=make_resolver({"evil.lab": ["8.8.8.8"]}),
    )
    assert gate.resolve_and_gate("evil.lab") == []


def test_resolver_error_fails_closed():
    gate = ScopeGate(
        in_scope=["10.10.10.0/24"],
        resolver=make_resolver({}, errors=("broken.lab",)),
    )
    assert gate.resolve_and_gate("broken.lab") == []


def test_name_only_scope_authorizes_resolved_ip():
    # No IP/CIDR declared: the name authorizes its resolved IPs (minus explicit exclusions).
    gate = ScopeGate(
        in_scope=["target.lab"],
        out_of_scope=["6.6.6.6"],
        resolver=make_resolver({"target.lab": ["192.168.50.9"]}),
    )
    assert gate.resolve_and_gate("target.lab") == ["192.168.50.9"]


def test_name_only_scope_still_honors_ip_exclusion():
    gate = ScopeGate(
        in_scope=["target.lab"],
        out_of_scope=["6.6.6.6"],
        resolver=make_resolver({"target.lab": ["6.6.6.6"]}),
    )
    assert gate.resolve_and_gate("target.lab") == []


def test_name_and_cidr_scope_bounds_to_cidr():
    # Both a name and a CIDR are declared: only IPs inside the CIDR pass (strict bounding).
    gate = ScopeGate(
        in_scope=["target.lab", "10.10.10.0/24"],
        resolver=make_resolver({"target.lab": ["192.168.1.9", "10.10.10.9"]}),
    )
    assert gate.resolve_and_gate("target.lab") == ["10.10.10.9"]


def test_explicitly_excluded_name_short_circuits():
    gate = ScopeGate(
        in_scope=["*.acme.com"],
        out_of_scope=["blog.acme.com"],
        resolver=make_resolver({"blog.acme.com": ["203.0.113.9"]}),
    )
    assert gate.resolve_and_gate("blog.acme.com") == []


def test_ip_literal_target_passes_through_gate():
    gate = ScopeGate(in_scope=["10.10.10.0/24"], out_of_scope=["10.10.10.1"])
    assert gate.resolve_and_gate("10.10.10.5") == ["10.10.10.5"]
    assert gate.resolve_and_gate("10.10.10.1") == []  # excluded
    assert gate.resolve_and_gate("8.8.8.8") == []      # outside scope


def _is_ip(token: str) -> bool:
    try:
        ipaddress.ip_address(token)
        return True
    except ValueError:
        return False
