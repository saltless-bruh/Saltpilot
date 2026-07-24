"""ReconRunner — orchestrates the fixed v1 pipeline with process hygiene (Task 2.4, R2/R8).

Governing principle: recon is best-effort and partial by nature, so a failure degrades *coverage*,
it does not break the engine. One tool / host / wave failing is a local event, never a global one.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from .config import Engagement
from .findings import Finding
from .normalize import build_alias_map, dedup, normalize
from .scope import ScopeGate
from .store import GraphStore
from .workbench import CoverageRecord, RawOutput, ReconOutcome, ToolInvocation, Workbench


def run_invocation(inv: ToolInvocation, timeout_secs: int) -> tuple[RawOutput, ReconOutcome]:
    """Execute one tool invocation as a constrained subprocess (R2.4).

    Subprocess discipline: argv list (no shell), hard wall-clock timeout, child reaped on
    completion or timeout, stdout/stderr captured. Never raises to the caller.
    """
    try:
        proc = subprocess.run(
            list(inv.argv),
            capture_output=True,
            text=True,
            timeout=timeout_secs,
        )
    except FileNotFoundError:
        return RawOutput.of("", stderr=f"{inv.tool} not found", exit_code=127), ReconOutcome.PERMANENT
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills and reaps the child before raising.
        partial = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return RawOutput.of(partial, stderr="timeout", exit_code=None), ReconOutcome.TRANSIENT

    raw = RawOutput.of(proc.stdout or "", stderr=proc.stderr or "", exit_code=proc.returncode)
    if proc.returncode != 0 and not (proc.stdout or "").strip():
        return raw, ReconOutcome.PERMANENT
    if not (proc.stdout or "").strip():
        return raw, ReconOutcome.EMPTY
    return raw, ReconOutcome.OK


@dataclass
class ReconResult:
    findings: list[Finding]
    coverage: list[CoverageRecord]
    persisted: dict = field(default_factory=dict)

    def coverage_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for record in self.coverage:
            summary[record.outcome.value] = summary.get(record.outcome.value, 0) + 1
        return summary


class ReconRunner:
    """Drives one or more workbenches, then normalizes -> dedups -> persists (single writer)."""

    def __init__(
        self,
        engagement: Engagement,
        gate: ScopeGate,
        store: GraphStore,
        workbenches: list[Workbench],
        executor=run_invocation,
    ) -> None:
        self.engagement = engagement
        self.gate = gate
        self.store = store
        self.workbenches = workbenches
        self.executor = executor

    def _plan(self) -> list[tuple[Workbench, str, dict]]:
        # v1 fixed pipeline: network discovery on the engagement target. Later slices expand this
        # into progressive waves and model-issued intents.
        plan: list[tuple[Workbench, str, dict]] = []
        for wb in self.workbenches:
            if wb.category == "network":
                plan.append((wb, "discover_services", {"host": self.engagement.target}))
        return plan

    def run(self) -> ReconResult:
        all_findings: list[Finding] = []
        coverage: list[CoverageRecord] = []
        resolutions: dict[str, list[str]] = {}

        for wb, intent, params in self._plan():
            result = wb.run(
                intent,
                params,
                self.gate,
                self.engagement.id,
                timeout_secs=self.engagement.recon.tool_timeout_secs,
                executor=self.executor,
            )
            all_findings.extend(result.findings)
            coverage.extend(result.coverage)
            resolutions.update(result.resolutions)

        alias_map = build_alias_map(resolutions)
        normalized = normalize(all_findings, alias_map=alias_map)
        deduped = dedup(normalized)

        persisted = self.store.persist_findings(self.engagement, deduped)
        self.store.log_run(
            self.engagement.id,
            kind="tool",
            detail={
                "coverage": [
                    {"tool": c.tool, "intent": c.intent, "target": c.target, "outcome": c.outcome.value,
                     "findings": c.finding_count, "detail": c.detail}
                    for c in coverage
                ],
                "persisted": persisted,
            },
        )
        return ReconResult(findings=deduped, coverage=coverage, persisted=persisted)


def build_network_recon(engagement: Engagement, store: GraphStore, executor=run_invocation) -> ReconRunner:
    """Wire a ReconRunner with the scope gate (from the engagement) and the network workbench."""
    from .adapters.nmap import NetworkWorkbench

    gate = ScopeGate(engagement.in_scope, engagement.out_of_scope)
    return ReconRunner(
        engagement=engagement,
        gate=gate,
        store=store,
        workbenches=[NetworkWorkbench(nmap_args=engagement.recon.nmap_args)],
        executor=executor,
    )
