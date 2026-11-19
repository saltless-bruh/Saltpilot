"""ScopeGate — the one control that fails closed (Requirement 1, design.md Section 1).

Scope discipline is the whole game: the expansion loop is powerful precisely because it is
automatic, which is exactly why a single scope-gating bug is the worst failure in the system.
Two rules define this module:

  1. **Fail closed.** Any error, ambiguity, or resolution failure resolves to *not in scope*.
     Neither public method raises to the caller.
  2. **The gate resolves hostnames itself and hands tools the gated IP, never the hostname.**
     Otherwise a tool's own internal DNS could reach an IP the gate never checked, silently
     bypassing scope (the "scope-resolution hole", a slice-blocking fix — tasks.md M1).
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

Resolver = Callable[[str], list[str]]


class ScopeVerdict(str, Enum):
    """Verdict for a single asset.

    IN_SCOPE      — authorized; may be scanned.
    OUT_OF_SCOPE  — not authorized (never in scope) OR any error/ambiguity (fail-closed default).
    SKIP          — deliberately carved out (matched an explicit out-of-scope entry). Distinct
                    from OUT_OF_SCOPE only for honest reporting; both mean "do not scan".
    """

    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    SKIP = "skip"


def _default_resolver(hostname: str) -> list[str]:
    """Resolve a hostname to a de-duplicated list of IP strings (IPv4 + IPv6)."""
    ips: list[str] = []
    for info in socket.getaddrinfo(hostname, None):
        ip = info[4][0]
        # getaddrinfo can suffix a scope id on link-local v6 (e.g. 'fe80::1%eth0'); drop it.
        ip = ip.split("%", 1)[0]
        if ip not in ips:
            ips.append(ip)
    return ips


def _is_ip(token: str) -> bool:
    try:
        ipaddress.ip_address(token)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class _DomainRule:
    """A compiled domain scope entry.

    wildcard=True  -> pattern is a leading-dot suffix ('.example.com') matching proper subdomains.
    wildcard=False -> exact host match only ('example.com' matches only 'example.com').
    """

    pattern: str
    wildcard: bool

    def matches(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        if self.wildcard:
            return host.endswith(self.pattern) and len(host) > len(self.pattern)
        return host == self.pattern


class ScopeGate:
    def __init__(
        self,
        in_scope: Iterable[str],
        out_of_scope: Iterable[str] | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._in_nets, self._in_domains = self._compile(in_scope)
        self._out_nets, self._out_domains = self._compile(out_of_scope or ())
        self._resolver = resolver or _default_resolver

    # ----------------------------------------------------------------- compilation
    @staticmethod
    def _compile(
        entries: Iterable[str],
    ) -> tuple[list[ipaddress._BaseNetwork], list[_DomainRule]]:
        nets: list[ipaddress._BaseNetwork] = []
        domains: list[_DomainRule] = []
        for raw in entries:
            entry = (raw or "").strip()
            if not entry:
                continue
            try:
                nets.append(ipaddress.ip_network(entry, strict=False))
                continue
            except ValueError:
                pass  # not an IP/CIDR -> treat as a domain rule
            low = entry.lower().rstrip(".")
            if low.startswith("*."):
                domains.append(_DomainRule(low[1:], wildcard=True))  # '*.example.com' -> '.example.com'
            else:
                domains.append(_DomainRule(low, wildcard=False))
        return nets, domains

    # ----------------------------------------------------------------- matching helpers
    @staticmethod
    def _ip_in(ip: str, nets: list[ipaddress._BaseNetwork]) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        # `addr in net` is False (not an error) across IPv4/IPv6 family mismatch.
        return any(addr in net for net in nets)

    def _domain_in(self, host: str, domains: list[_DomainRule]) -> bool:
        return any(rule.matches(host) for rule in domains)

    # ----------------------------------------------------------------- public API
    def check(self, asset: str) -> ScopeVerdict:
        """Classify a single asset (IP or hostname). Explicit exclusion wins; never raises."""
        try:
            token = (asset or "").strip()
            if not token:
                return ScopeVerdict.OUT_OF_SCOPE
            if _is_ip(token):
                if self._ip_in(token, self._out_nets):
                    return ScopeVerdict.SKIP
                if self._ip_in(token, self._in_nets):
                    return ScopeVerdict.IN_SCOPE
                return ScopeVerdict.OUT_OF_SCOPE
            if self._domain_in(token, self._out_domains):
                return ScopeVerdict.SKIP
            if self._domain_in(token, self._in_domains):
                return ScopeVerdict.IN_SCOPE
            return ScopeVerdict.OUT_OF_SCOPE
        except Exception:
            return ScopeVerdict.OUT_OF_SCOPE  # fail closed (R1.3)

    def resolve_and_gate(self, target: str) -> list[str]:
        """Resolve a target HERE, gate each resulting IP, and return only the in-scope IPs.

        Tools are handed these IPs, never the hostname. Returns [] on any failure or when nothing
        is authorized (fail closed). Authorization rule, most-restrictive-that-passes-the-spec:

          * An explicit out-of-scope match (by name or by IP) always drops the asset.
          * An IP literal passes iff it is IN_SCOPE by `check`.
          * A hostname is resolved; each resolved IP passes iff it is not explicitly excluded AND
            either (a) it falls inside a declared in-scope IP/CIDR, or (b) no IP/CIDR ranges were
            declared at all and the hostname itself matched an in-scope domain entry.

        Rule (b) supports name-only scoping (operator authorized "this host, wherever it lives")
        while rule (a) makes declared CIDRs bound the engagement: when ranges are given, a name that
        resolves outside them is dropped. Both directly satisfy R1.2 ("a hostname resolving to an
        out-of-scope IP is rejected").
        """
        try:
            token = (target or "").strip()
            if not token:
                return []

            if _is_ip(token):
                return [token] if self.check(token) is ScopeVerdict.IN_SCOPE else []

            # Hostname path. Reject outright if the name itself is explicitly excluded.
            if self._domain_in(token, self._out_domains):
                return []

            hostname_authorized = self._domain_in(token, self._in_domains)
            has_in_nets = bool(self._in_nets)

            try:
                resolved = self._resolver(token)
            except Exception:
                return []  # resolution failure -> fail closed (R1.2)

            authorized: list[str] = []
            for ip in resolved:
                if not _is_ip(ip):
                    continue
                if self._ip_in(ip, self._out_nets):
                    continue  # explicit IP exclusion wins
                if self._ip_in(ip, self._in_nets) or (hostname_authorized and not has_in_nets):
                    if ip not in authorized:
                        authorized.append(ip)
            return authorized
        except Exception:
            return []  # fail closed
