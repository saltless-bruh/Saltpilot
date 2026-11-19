"""Deterministic normalization — identity + provenance merge, no model (Task 2.5, R3.3).

The slice-blocking host-identity fix lives here: a machine seen as an IP by one tool and as a
hostname by another must collapse to ONE asset, and the scanner's service label is an attribute
(not identity). Getting this right is what makes idempotent re-run (R5.3) actually hold.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Iterable
from dataclasses import replace

from .findings import Finding


def _is_ip(token: str) -> bool:
    try:
        ipaddress.ip_address(token)
        return True
    except ValueError:
        return False


def build_alias_map(resolutions: dict[str, list[str]]) -> dict[str, str]:
    """From the gate's resolutions (host -> gated IPs), build observed_host -> canonical_host.

    Canonical identity is the first gated IP; the IP maps to itself. This is what unifies a host
    seen as both a hostname and an IP without any new DNS lookups (the gate already resolved it).
    """
    alias: dict[str, str] = {}
    for name, ips in resolutions.items():
        if not ips:
            continue
        canonical = ips[0]
        alias.setdefault(name, canonical)
        for ip in ips:
            alias.setdefault(ip, ip)
    return alias


def canonicalize_host(
    host: str,
    alias_map: dict[str, str] | None = None,
    resolver: Callable[[str], list[str]] | None = None,
) -> str:
    """Resolve a host string to one stable identity.

    Order: an explicit alias wins; an IP is its own identity; otherwise a best-effort resolver
    (injected for tests) maps a hostname to its IP. If nothing resolves, the host string is its own
    identity (never raises).
    """
    if not host:
        return host
    if alias_map and host in alias_map:
        return alias_map[host]
    if _is_ip(host):
        return host
    if resolver is not None:
        try:
            ips = resolver(host)
        except Exception:
            ips = []
        if ips:
            return ips[0]
    return host


def normalize(
    findings: Iterable[Finding],
    alias_map: dict[str, str] | None = None,
    resolver: Callable[[str], list[str]] | None = None,
) -> list[Finding]:
    """Rewrite each finding's asset_host to its canonical identity."""
    out: list[Finding] = []
    for f in findings:
        canonical = canonicalize_host(f.asset_host, alias_map=alias_map, resolver=resolver)
        out.append(replace(f, asset_host=canonical) if canonical != f.asset_host else f)
    return out


def _identity(f: Finding) -> tuple:
    # (canonical_host, port, kind, url_path) — service label deliberately excluded.
    return (f.asset_host, f.port, f.kind, f.detail.get("url_path"))


def dedup(findings: Iterable[Finding]) -> list[Finding]:
    """Collapse findings sharing an identity key, unioning provenance."""
    groups: dict[tuple, Finding] = {}
    order: list[tuple] = []
    for f in findings:
        key = _identity(f)
        if key not in groups:
            groups[key] = f
            order.append(key)
            continue
        base = groups[key]
        provenance = base.detail.get("provenance") or [{"tool": base.source_tool, "raw_ref": base.raw_ref}]
        provenance = provenance + [{"tool": f.source_tool, "raw_ref": f.raw_ref}]
        merged_detail = {**base.detail, **f.detail, "provenance": provenance}
        # Keep the higher-confidence finding's core fields; carry merged detail forward.
        winner = base if base.confidence >= f.confidence else f
        groups[key] = replace(winner, detail=merged_detail)
    return [groups[k] for k in order]
