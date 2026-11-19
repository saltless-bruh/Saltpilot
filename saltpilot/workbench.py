"""The Workbench layer — category tool layers behind an intent interface (Auto-Recon Section 4.1).

The caller expresses an *intent* + typed params; a Workbench picks the tool for the installed
version, resolves+gates hosts to IPs itself, renders the exact command, and normalizes output.
The caller never names a tool or a flag — so a stale-tool-knowledge model (in later slices) cannot
emit a dead command, because it never emits a command at all (R2.6).

This module holds the shared types + protocols. Concrete workbenches live in `adapters/`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from .findings import Finding
from .scope import ScopeGate


# ------------------------------------------------------------------ intent catalog
@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str                 # 'host' | 'hosts' | 'ports' | 'int' | ...
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class IntentSpec:
    """One entry in the intent catalog — what you can ask a workbench to do."""

    name: str
    description: str
    params: tuple[ParamSpec, ...] = ()


# ------------------------------------------------------------------ tool I/O types
@dataclass(frozen=True)
class ToolStatus:
    name: str
    available: bool
    version: str | None = None
    detail: str = ""
    install_hint: str | None = None


@dataclass(frozen=True)
class ToolInvocation:
    tool: str
    argv: tuple[str, ...]
    intent: str
    engagement_id: str        # execution context threaded to stamp findings (not a model param)
    gated_ips: tuple[str, ...]
    output_format: str        # 'nmap-xml' | 'httpx-json'
    stdin: str | None = None  # data piped to the tool's stdin (httpx reads targets there)


@dataclass(frozen=True)
class RawOutput:
    stdout: str
    stderr: str = ""
    exit_code: int | None = None
    ref: str = ""             # content-hash evidence reference (provenance)

    @classmethod
    def of(cls, stdout: str, stderr: str = "", exit_code: int | None = None) -> "RawOutput":
        digest = hashlib.sha1((stdout or "").encode("utf-8", "replace")).hexdigest()[:16]
        return cls(stdout=stdout or "", stderr=stderr or "", exit_code=exit_code, ref=f"sha1:{digest}")


# ------------------------------------------------------------------ outcomes / coverage
class ReconOutcome(str, Enum):
    OK = "ok"
    TRANSIENT = "transient"   # timeout, blip — retryable
    PERMANENT = "permanent"   # tool missing, unparseable — fall back
    EMPTY = "empty"           # ran, nothing found (a valid result)
    SKIPPED = "skipped"       # gated out / no in-scope IPs


@dataclass(frozen=True)
class CoverageRecord:
    """One line of the coverage ledger — what ran, on what, and how it ended (R8.1)."""

    tool: str
    intent: str
    target: str
    outcome: ReconOutcome
    finding_count: int = 0
    detail: str = ""


@dataclass
class WorkbenchResult:
    findings: list[Finding]
    coverage: list[CoverageRecord]
    resolutions: dict[str, list[str]] = field(default_factory=dict)  # host -> gated ips (for aliasing)


# ------------------------------------------------------------------ protocols
@runtime_checkable
class ToolAdapter(Protocol):
    name: str

    def is_available(self) -> ToolStatus: ...

    def render(
        self, intent: str, params: dict, gated_ips: list[str], engagement_id: str
    ) -> list[ToolInvocation]: ...

    def parse(self, invocation: ToolInvocation, raw: RawOutput) -> list[Finding]: ...


@runtime_checkable
class Workbench(Protocol):
    category: str

    def intents(self) -> list[IntentSpec]: ...

    def run(
        self,
        intent: str,
        params: dict,
        gate: ScopeGate,
        engagement_id: str,
        *,
        timeout_secs: int,
        executor,
    ) -> WorkbenchResult: ...
