"""Web workbench — ProjectDiscovery httpx behind the `probe_web` intent (Tasks 3.1, 3.2).

The slice-blocking httpx/nmap-coupling fix lives here: the web workbench probes **all** open ports
nmap found and lets httpx decide what is web — it does not filter by nmap's service label. A web
service on an odd or mislabeled port would otherwise be silently lost. Workbenches share *facts*
(open ports), not *classifications* (design.md Section 2, R2.2).

Note: `httpx` the name is ambiguous — this is ProjectDiscovery's recon tool, not the Python HTTP
library that may shadow the same binary name. `is_available` verifies it found the right tool.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

from ..findings import Finding
from ..scope import ScopeGate
from ..workbench import (
    CoverageRecord,
    IntentSpec,
    ParamSpec,
    RawOutput,
    ReconOutcome,
    ToolInvocation,
    ToolStatus,
    WorkbenchResult,
)

_HTTPX_INSTALL_HINT = "install ProjectDiscovery httpx (`go install github.com/projectdiscovery/httpx/cmd/httpx@latest`)"
_VERSION_RE = re.compile(r"Current Version:\s*(v[\d.]+)")


class HttpxAdapter:
    name = "httpx"

    def __init__(self, binary: str = "httpx", probe_timeout: int = 10) -> None:
        self.binary = binary
        self.probe_timeout = probe_timeout

    def is_available(self) -> ToolStatus:
        if not shutil.which(self.binary) and "/" not in self.binary:
            return ToolStatus(self.name, available=False, detail="not in PATH", install_hint=_HTTPX_INSTALL_HINT)
        try:
            out = subprocess.run([self.binary, "-version"], capture_output=True, text=True, timeout=10)
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            return ToolStatus(self.name, available=False, detail=f"version check failed: {exc}", install_hint=_HTTPX_INSTALL_HINT)
        blob = f"{out.stdout}\n{out.stderr}"
        if "projectdiscovery" not in blob.lower():
            # Found a binary named httpx, but it is not ProjectDiscovery httpx (e.g. the Python
            # httpx[cli]). Treat it as a capability gap so recon flags it rather than misparsing.
            return ToolStatus(
                self.name,
                available=False,
                detail="found a different 'httpx' (not ProjectDiscovery)",
                install_hint=_HTTPX_INSTALL_HINT,
            )
        match = _VERSION_RE.search(blob)
        return ToolStatus(self.name, available=True, version=match.group(1) if match else None)

    def render(self, intent: str, params: dict, gated_ips: list[str], engagement_id: str) -> list[ToolInvocation]:
        if intent != "probe_web":
            raise ValueError(f"httpx adapter does not serve intent '{intent}'")
        ports = params.get("ports") or []
        # Probe every open port on every gated IP; httpx decides which are actually web.
        targets = [f"{ip}:{port}" for ip in gated_ips for port in ports]
        if not targets:
            return []
        argv = [
            self.binary, "-json", "-silent", "-sc", "-title", "-td", "-server",
            "-timeout", str(self.probe_timeout), "-no-color",
        ]
        return [
            ToolInvocation(
                tool="httpx",
                argv=tuple(argv),
                intent=intent,
                engagement_id=engagement_id,
                gated_ips=tuple(gated_ips),
                output_format="httpx-json",
                stdin="\n".join(targets) + "\n",
            )
        ]

    def parse(self, invocation: ToolInvocation, raw: RawOutput) -> list[Finding]:
        findings: list[Finding] = []
        for line in (raw.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip a malformed line; never crash the pipeline (R3.4)
            if not isinstance(rec, dict) or rec.get("failed"):
                continue

            host = rec.get("host") or rec.get("host_ip")
            port = rec.get("port")
            if not host or port is None:
                continue
            try:
                port = int(port)
            except (TypeError, ValueError):
                continue

            scheme = rec.get("scheme") or "http"
            url_path = rec.get("path") or "/"
            detail = {
                "url": rec.get("url"),
                "scheme": scheme,
                "status_code": rec.get("status_code"),
                "title": rec.get("title"),
                "webserver": rec.get("webserver"),
                "tech": rec.get("tech"),
                "content_type": rec.get("content_type"),
                "url_path": url_path,  # part of the web_endpoint identity key
            }
            if rec.get("tls"):
                detail["tls"] = rec.get("tls")

            findings.append(
                Finding(
                    engagement_id=invocation.engagement_id,
                    asset_host=host,
                    port=port,
                    service=scheme,
                    product=rec.get("webserver"),
                    version=None,
                    kind="web_endpoint",
                    detail=detail,
                    source_tool="httpx",
                    raw_ref=f"{raw.ref}#{host}:{port}{url_path}",
                    confidence=0.9,
                    scope_status="in_scope",
                    observed_at=rec.get("timestamp") or "",
                )
            )
        return findings


class WebWorkbench:
    category = "web"

    def __init__(self, httpx_binary: str = "httpx", probe_timeout: int = 10) -> None:
        self.adapter = HttpxAdapter(binary=httpx_binary, probe_timeout=probe_timeout)

    def intents(self) -> list[IntentSpec]:
        return [
            IntentSpec(
                name="probe_web",
                description="Probe open ports for web services (tech, title, status, TLS).",
                params=(
                    ParamSpec("host", "host", required=True, description="an in-scope host/IP"),
                    ParamSpec("ports", "ports", required=True, description="open ports to probe (ALL of them)"),
                ),
            )
        ]

    def run(
        self,
        intent: str,
        params: dict,
        gate: ScopeGate,
        engagement_id: str,
        *,
        timeout_secs: int,
        executor,
    ) -> WorkbenchResult:
        host = params["host"]
        ports = params.get("ports") or []
        gated_ips = gate.resolve_and_gate(host)  # defense in depth: re-gate before probing
        resolutions = {host: gated_ips}

        if not gated_ips or not ports:
            return WorkbenchResult(
                [],
                [CoverageRecord("httpx", intent, host, ReconOutcome.SKIPPED, 0, "no gated IPs or no open ports")],
                resolutions,
            )

        status = self.adapter.is_available()
        if not status.available:  # R2.3: missing tool -> capability gap + skip + continue
            return WorkbenchResult(
                [],
                [CoverageRecord("httpx", intent, host, ReconOutcome.PERMANENT, 0, f"capability gap: {status.detail}")],
                resolutions,
            )

        findings: list[Finding] = []
        coverage: list[CoverageRecord] = []
        for inv in self.adapter.render(intent, params, gated_ips, engagement_id):
            raw, outcome = executor(inv, timeout_secs)
            if outcome is ReconOutcome.OK:
                try:
                    parsed = self.adapter.parse(inv, raw)
                except Exception as exc:
                    coverage.append(CoverageRecord("httpx", intent, host, ReconOutcome.PERMANENT, 0, f"parse error: {exc}"))
                    continue
                findings.extend(parsed)
                result = ReconOutcome.OK if parsed else ReconOutcome.EMPTY
                coverage.append(CoverageRecord("httpx", intent, host, result, len(parsed), ""))
            else:
                coverage.append(CoverageRecord("httpx", intent, host, outcome, 0, (raw.stderr or "")[:200]))
        return WorkbenchResult(findings, coverage, resolutions)
