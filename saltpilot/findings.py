"""Typed data models for the recon pipeline — Finding (what a tool saw) and Asset (an identity).

Finding is produced by deterministic parsers (never a model); Asset is the persisted identity a
finding attaches to. Identity is `(canonical_host, port)` (+ url_path for web endpoints); the
scanner's service label is an *attribute, not identity*, so a re-scan that reclassifies a port
updates the asset instead of spawning a duplicate (design.md Section 4, R3.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    engagement_id: str
    asset_host: str            # ip or hostname (canonicalized during normalize)
    port: int | None
    service: str | None        # e.g. 'http', 'ssh' — an attribute, not identity
    product: str | None        # e.g. 'nginx', 'OpenSSH'
    version: str | None
    kind: str                  # 'service' | 'web_endpoint' | 'tech'
    detail: dict               # tool-specific extras (state, extrainfo, cpe, title, tls, ...)
    source_tool: str           # 'nmap' | 'httpx'
    raw_ref: str               # reference to the raw output slice (provenance)
    confidence: float          # 0..1 (parser confidence; banners lie)
    scope_status: str          # 'in_scope' | 'skipped_out_of_scope'
    observed_at: str           # ISO 8601


@dataclass(frozen=True)
class Asset:
    engagement_id: str
    canonical_host: str        # unified IP<->hostname identity
    kind: str                  # 'host' | 'service' | 'web_endpoint'
    port: int | None = None
    url_path: str | None = None
    service: str | None = None  # scanner's guess: an attribute, not identity
    scope_status: str = "in_scope"


@dataclass(frozen=True)
class Fact:
    """A retrieved unit of ground truth for the copilot to answer over (Copilot Section 7).

    Carries a citation `id`, a human-readable `text` for the prompt, and the named entities it
    contains — which are exactly what the grounding guard cross-checks an answer against.
    """

    id: str                    # citation id, e.g. 'asset:12' / 'finding:5' / 'interp:3'
    kind: str                  # 'asset' | 'finding' | 'interpretation'
    text: str
    hosts: tuple[str, ...] = ()
    ports: tuple[int, ...] = ()
    cves: tuple[str, ...] = ()
