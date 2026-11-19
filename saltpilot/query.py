"""Copilot query — a grounded answer over the engagement graph (Milestone 6; design.md Section 8;
Copilot Section 7).

The load-bearing piece is `ground_guard`: a deterministic backstop that extracts the named entities
(hosts, ports, CVEs) from the model's answer and cross-checks them against the retrieved fact set,
neutralizing any it invented. A grounding prompt can only *reduce* invention; the guard makes
"no invented assets" an ENFORCED invariant (R6.2) — the same model-proposes/parser-disposes
discipline as recon's CVE validation, and load-bearing given the reasoner's raw hallucination rate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from collections.abc import Iterable

from .findings import Fact
from .models import ProviderError, Role

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_HOST_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)
_CITATION_RE = re.compile(r"\[?\b(?:asset|finding|interp|interpretation)\s*:\s*\d+\]?", re.IGNORECASE)
_PORT_RES = (
    re.compile(r"\bport\s+(\d{1,5})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,5})/(?:tcp|udp)\b", re.IGNORECASE),
    re.compile(r"(?:\d{1,3}(?:\.\d{1,3}){3}|[a-z][a-z0-9.\-]+):(\d{2,5})\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class Answer:
    text: str
    grounded: list[str]            # fact ids the answer drew on / cited (R6.5)
    flagged: list[str]             # entities the guard caught as not-in-facts
    reasoner: str                  # who answered, e.g. 'ollama/qwen3-...' or 'none' (R6.3/R6.5)
    fell_back: bool = False
    no_facts: bool = False


def _allowed(facts: Iterable[Fact]) -> tuple[set[str], set[int], set[str]]:
    hosts: set[str] = set()
    ports: set[int] = set()
    cves: set[str] = set()
    for f in facts:
        hosts |= {h.lower() for h in f.hosts}
        ports |= set(f.ports)
        cves |= {c.upper() for c in f.cves}
    return hosts, ports, cves


def ground_guard(answer: str, facts: list[Fact]) -> tuple[str, list[str]]:
    """Extract hosts/ports/CVEs from `answer`; neutralize any not present in `facts` (R6.2).

    An invented entity is replaced with `[unverified: X]` so it can never reach the operator as an
    unqualified claim, and returned in the flagged list. Fact-citation tokens (`[finding:3]`) are
    ignored so a citation id is never mistaken for an invented port.
    """
    hosts, ports, cves = _allowed(facts)
    scan = _CITATION_RE.sub(" ", answer)  # don't let citation ids look like ports

    invented: list[str] = []

    def _flag(token: str) -> None:
        if token not in invented:
            invented.append(token)

    for m in _CVE_RE.finditer(scan):
        if m.group(0).upper() not in cves:
            _flag(m.group(0))
    for m in _IP_RE.finditer(scan):
        if m.group(0).lower() not in hosts:
            _flag(m.group(0))
    for m in _HOST_RE.finditer(scan):
        if m.group(0).lower() not in hosts:
            _flag(m.group(0))
    for rx in _PORT_RES:
        for m in rx.finditer(scan):
            if int(m.group(1)) not in ports:
                _flag(m.group(1))

    checked = answer
    for token in invented:
        checked = re.sub(rf"(?<!\[unverified: ){re.escape(token)}", f"[unverified: {token}]", checked)
    return checked, sorted(set(invented))


SYSTEM_PROMPT = (
    "You are a penetration-testing copilot answering questions about ONE authorized engagement. "
    "Answer ONLY using the numbered facts provided. Do NOT name any host, IP, port, or CVE that is "
    "not present in those facts — a deterministic guard verifies every entity you name and marks "
    "invented ones. Cite the facts you use by their id in square brackets, e.g. [finding:3]. "
    "If the facts do not cover the question, reply exactly: No relevant facts found."
)


def grounding_prompt(question: str, facts: list[Fact]) -> tuple[str, str]:
    lines = [f"[{f.id}] {f.text}" for f in facts]
    user = "FACTS:\n" + "\n".join(lines) + f"\n\nQUESTION: {question}"
    return SYSTEM_PROMPT, user


class CopilotQuery:
    def __init__(self, store, engagement_id: str) -> None:
        self.store = store
        self.engagement_id = engagement_id

    def answer(self, question: str, model) -> Answer:
        facts = self.store.facts_for_query(self.engagement_id, question)
        if not facts:  # R6.4 — say so plainly rather than invent
            ans = Answer("No relevant facts found.", grounded=[], flagged=[], reasoner="none", no_facts=True)
            self._log(question, facts, ans)
            return ans

        system, user = grounding_prompt(question, facts)
        try:
            completion = model.complete(Role.REASONING, user, max_tokens=800, system=system)
        except ProviderError as exc:
            ans = Answer(f"(reasoner unavailable: {exc})", grounded=[], flagged=[], reasoner="unavailable")
            self._log(question, facts, ans)
            return ans

        checked, flagged = ground_guard(completion.text, facts)
        grounded = _grounded_fact_ids(checked, facts)
        ans = Answer(
            text=checked,
            grounded=grounded,
            flagged=flagged,
            reasoner=f"{completion.provider}/{completion.model}",
            fell_back=completion.fell_back,
        )
        self._log(question, facts, ans)
        return ans

    def _log(self, question: str, facts: list[Fact], ans: Answer) -> None:
        self.store.log_run(
            self.engagement_id,
            kind="query",
            detail={
                "question": question,
                "facts": [f.id for f in facts],
                "reasoner": ans.reasoner,
                "fell_back": ans.fell_back,
                "grounded": ans.grounded,
                "flagged": ans.flagged,
                "answer": ans.text,
            },
        )


def _grounded_fact_ids(answer: str, facts: list[Fact]) -> list[str]:
    """Which facts the answer drew on: cited by id, or whose host/port/CVE appears in the answer."""
    low = answer.lower()
    grounded: list[str] = []
    for f in facts:
        if f.id.lower() in low:
            grounded.append(f.id)
            continue
        entities = list(f.hosts) + [str(p) for p in f.ports] + list(f.cves)
        if any(str(e).lower() in low for e in entities):
            grounded.append(f.id)
    return grounded
