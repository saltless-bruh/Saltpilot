"""ReconRunner — orchestrates the fixed v1 pipeline with process hygiene (Tasks 2.4, 3.3; R2/R8).

Governing principle: recon is best-effort and partial by nature, so a failure degrades *coverage*,
it does not break the engine. One tool / host / wave failing is a local event, never a global one.

The pipeline runs adapters in sequence and feeds each from the last: nmap discovers open ports,
then httpx probes ALL of them (the tool-feeds-tool pattern). httpx's feed is every open port nmap
found, not just those nmap labeled http — workbenches share facts (open ports), not classifications.
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
    completion or timeout, stdout/stderr captured, optional stdin piped in. Never raises.
    """
    try:
        proc = subprocess.run(
            list(inv.argv),
            input=inv.stdin,
            capture_output=True,
            text=True,
            timeout=timeout_secs,
        )
    except FileNotFoundError:
        return RawOutput.of("", stderr=f"{inv.tool} not found", exit_code=127), ReconOutcome.PERMANENT
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return RawOutput.of(partial, stderr="timeout", exit_code=None), ReconOutcome.TRANSIENT

    raw = RawOutput.of(proc.stdout or "", stderr=proc.stderr or "", exit_code=proc.returncode)
    if proc.returncode != 0 and not (proc.stdout or "").strip():
        return raw, ReconOutcome.PERMANENT
    if not (proc.stdout or "").strip():
        return raw, ReconOutcome.EMPTY
    return raw, ReconOutcome.OK


def web_feed(findings: list[Finding]) -> dict[str, list[str]]:
    """Group open ports by host to feed the web workbench.

    Every open port is included regardless of nmap's service label — this is the httpx/nmap
    decoupling fix (R2.2): a web service on an odd or mislabeled port must not be filtered out.
    """
    feed: dict[str, set[int]] = {}
    for f in findings:
        if f.kind == "service" and f.port is not None:
            feed.setdefault(f.asset_host, set()).add(f.port)
    return {host: [str(p) for p in sorted(ports)] for host, ports in feed.items()}


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
    """Runs the network stage, feeds the web stage from it, then normalize -> dedup -> persist."""

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

    def _by_category(self, category: str) -> list[Workbench]:
        return [wb for wb in self.workbenches if wb.category == category]

    def _dispatch(self, wb: Workbench, intent: str, params: dict):
        return wb.run(
            intent,
            params,
            self.gate,
            self.engagement.id,
            timeout_secs=self.engagement.recon.tool_timeout_secs,
            executor=self.executor,
        )

    def run(self) -> ReconResult:
        coverage: list[CoverageRecord] = []
        resolutions: dict[str, list[str]] = {}

        # Stage 1 — network discovery on the engagement target.
        net_findings: list[Finding] = []
        for wb in self._by_category("network"):
            result = self._dispatch(wb, "discover_services", {"host": self.engagement.target})
            net_findings.extend(result.findings)
            coverage.extend(result.coverage)
            resolutions.update(result.resolutions)

        # Canonicalize hosts before building the feed so ports group under one identity.
        net_findings = normalize(net_findings, alias_map=build_alias_map(resolutions))

        # Stage 2 — web probing, fed by ALL open ports from stage 1 (not filtered by service label).
        web_findings: list[Finding] = []
        web_workbenches = self._by_category("web")
        if web_workbenches:
            for host, ports in web_feed(net_findings).items():
                for wb in web_workbenches:
                    result = self._dispatch(wb, "probe_web", {"host": host, "ports": ports})
                    web_findings.extend(result.findings)
                    coverage.extend(result.coverage)
                    resolutions.update(result.resolutions)

        # Combine, normalize, dedup, persist (single writer).
        all_findings = net_findings + web_findings
        normalized = normalize(all_findings, alias_map=build_alias_map(resolutions))
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
    """Wire a network-only ReconRunner (nmap). Used where web probing is not wanted."""
    from .adapters.nmap import NetworkWorkbench

    gate = ScopeGate(engagement.in_scope, engagement.out_of_scope)
    return ReconRunner(
        engagement=engagement,
        gate=gate,
        store=store,
        workbenches=[NetworkWorkbench(nmap_args=engagement.recon.nmap_args)],
        executor=executor,
    )


def build_recon(
    engagement: Engagement,
    store: GraphStore,
    executor=run_invocation,
    *,
    httpx_binary: str = "httpx",
) -> ReconRunner:
    """Wire the full v1 recon: network (nmap) + web (httpx), fed in sequence."""
    from .adapters.httpx import WebWorkbench
    from .adapters.nmap import NetworkWorkbench

    gate = ScopeGate(engagement.in_scope, engagement.out_of_scope)
    return ReconRunner(
        engagement=engagement,
        gate=gate,
        store=store,
        workbenches=[
            NetworkWorkbench(nmap_args=engagement.recon.nmap_args),
            WebWorkbench(httpx_binary=httpx_binary),
        ],
        executor=executor,
    )
