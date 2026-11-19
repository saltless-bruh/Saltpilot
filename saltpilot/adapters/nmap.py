"""Network workbench — nmap behind the `discover_services` intent (Tasks 2.1, 2.2).

The adapter owns all tool-specific knowledge (flags, XML shape, parsing); the workbench owns the
intent contract and the scope discipline (resolve+gate hosts, hand nmap IPs, never hostnames).

Hostile-output defense (Auto-Recon Section 5.6): nmap XML is captured from an adversarial target,
so it is parsed with defusedxml (billion-laughs / external-entity hardening) and treated as a
failed task on a parse error, never a crash.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from datetime import datetime, timezone

import defusedxml.ElementTree as ET

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

_NMAP_INSTALL_HINT = "install nmap (e.g. `apt-get install nmap` / `brew install nmap`)"


def _epoch_to_iso(value: str | None) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _recover_partial(xml_text: str) -> str | None:
    """Salvage complete <host> blocks from a truncated nmap stream (graceful partial parse, R3.4).

    A scan killed mid-run yields non-well-formed XML. Cut to the last complete </host> and close
    the root so the hosts that *did* finish are still parseable; return None if not even one host
    completed.
    """
    marker = "</host>"
    idx = xml_text.rfind(marker)
    if idx == -1:
        return None
    return xml_text[: idx + len(marker)] + "\n</nmaprun>"


class NmapAdapter:
    name = "nmap"

    def __init__(self, nmap_args: str = "-sV -T4") -> None:
        self.nmap_args = nmap_args

    def is_available(self) -> ToolStatus:
        path = shutil.which("nmap")
        if not path:
            return ToolStatus(self.name, available=False, detail="not in PATH", install_hint=_NMAP_INSTALL_HINT)
        try:
            out = subprocess.run(["nmap", "--version"], capture_output=True, text=True, timeout=10)
            first = (out.stdout or "").splitlines()[0] if out.stdout else ""
            version = first.replace("Nmap version", "").strip().split(" ")[0] or None
            return ToolStatus(self.name, available=True, version=version, detail=first.strip())
        except Exception as exc:  # pragma: no cover - defensive
            return ToolStatus(self.name, available=False, detail=f"version check failed: {exc}", install_hint=_NMAP_INSTALL_HINT)

    def render(self, intent: str, params: dict, gated_ips: list[str], engagement_id: str) -> list[ToolInvocation]:
        if intent != "discover_services":
            raise ValueError(f"nmap adapter does not serve intent '{intent}'")
        if not gated_ips:
            return []
        # -oX - writes XML to stdout so there is no temp file to reap. IPs are gated; argv is a
        # list (shell=False), so nothing untrusted is interpolated into a shell.
        argv = ["nmap", *shlex.split(self.nmap_args), "-oX", "-", *gated_ips]
        return [
            ToolInvocation(
                tool="nmap",
                argv=tuple(argv),
                intent=intent,
                engagement_id=engagement_id,
                gated_ips=tuple(gated_ips),
                output_format="nmap-xml",
            )
        ]

    def parse(self, invocation: ToolInvocation, raw: RawOutput) -> list[Finding]:
        text = raw.stdout or ""
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            recovered = _recover_partial(text)
            if recovered is None:
                return []
            try:
                root = ET.fromstring(recovered)
            except ET.ParseError:
                return []
        return self._findings_from_root(root, invocation, raw)

    def _findings_from_root(self, root, invocation: ToolInvocation, raw: RawOutput) -> list[Finding]:
        findings: list[Finding] = []
        for host in root.findall("host"):
            status = host.find("status")
            if status is not None and status.get("state") not in (None, "up"):
                continue

            addr = None
            for address in host.findall("address"):
                if address.get("addrtype") in ("ipv4", "ipv6"):
                    addr = address.get("addr")
                    break
            if not addr:
                continue

            hostnames = [h.get("name") for h in host.findall("hostnames/hostname") if h.get("name")]
            observed_at = _epoch_to_iso(host.get("starttime") or root.get("start"))

            ports = host.find("ports")
            if ports is None:
                continue
            for port in ports.findall("port"):
                state = port.find("state")
                if state is None or state.get("state") != "open":
                    continue  # only open ports become findings; closed/filtered are not surface

                portid = int(port.get("portid"))
                detail: dict = {"protocol": port.get("protocol"), "state": "open"}
                service = product = version = None
                confidence = 0.5

                svc = port.find("service")
                if svc is not None:
                    service = svc.get("name")
                    product = svc.get("product")
                    version = svc.get("version")
                    if svc.get("method"):
                        detail["method"] = svc.get("method")
                    if svc.get("extrainfo"):
                        detail["extrainfo"] = svc.get("extrainfo")
                    cpes = [c.text for c in svc.findall("cpe") if c.text]
                    if cpes:
                        detail["cpe"] = cpes
                    conf = svc.get("conf")
                    if conf is not None and conf.isdigit():
                        confidence = min(int(conf) / 10.0, 1.0)
                if hostnames:
                    detail["hostnames"] = hostnames

                findings.append(
                    Finding(
                        engagement_id=invocation.engagement_id,
                        asset_host=addr,
                        port=portid,
                        service=service,
                        product=product,
                        version=version,
                        kind="service",
                        detail=detail,
                        source_tool="nmap",
                        raw_ref=f"{raw.ref}#{addr}:{portid}",
                        confidence=confidence,
                        scope_status="in_scope",
                        observed_at=observed_at,
                    )
                )
        return findings


class NetworkWorkbench:
    category = "network"

    def __init__(self, nmap_args: str = "-sV -T4") -> None:
        self.adapter = NmapAdapter(nmap_args=nmap_args)

    def intents(self) -> list[IntentSpec]:
        return [
            IntentSpec(
                name="discover_services",
                description="Discover open ports and their services/versions on a host.",
                params=(ParamSpec("host", "host", required=True, description="a hostname, IP, or CIDR in scope"),),
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
        gated_ips = gate.resolve_and_gate(host)  # workbench resolves+gates; hands nmap IPs only
        resolutions = {host: gated_ips}

        if not gated_ips:
            return WorkbenchResult(
                [],
                [CoverageRecord("nmap", intent, host, ReconOutcome.SKIPPED, 0, "no in-scope IPs after gating")],
                resolutions,
            )

        status = self.adapter.is_available()
        if not status.available:
            return WorkbenchResult(
                [],
                [CoverageRecord("nmap", intent, host, ReconOutcome.PERMANENT, 0, f"tool unavailable: {status.install_hint}")],
                resolutions,
            )

        findings: list[Finding] = []
        coverage: list[CoverageRecord] = []
        for inv in self.adapter.render(intent, params, gated_ips, engagement_id):
            raw, outcome = executor(inv, timeout_secs)
            if outcome is ReconOutcome.OK:
                try:
                    parsed = self.adapter.parse(inv, raw)
                except Exception as exc:  # hardened: a parse failure degrades coverage, never crashes
                    coverage.append(CoverageRecord("nmap", intent, host, ReconOutcome.PERMANENT, 0, f"parse error: {exc}"))
                    continue
                findings.extend(parsed)
                result = ReconOutcome.OK if parsed else ReconOutcome.EMPTY
                coverage.append(CoverageRecord("nmap", intent, host, result, len(parsed), ""))
            else:
                coverage.append(CoverageRecord("nmap", intent, host, outcome, 0, (raw.stderr or "")[:200]))
        return WorkbenchResult(findings, coverage, resolutions)
