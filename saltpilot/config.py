"""Engagement configuration — engagement.toml -> a typed, immutable Engagement (Task 0.3).

The reasoner is selected by engagement *kind*, never a per-call convenience: 'practice' teaches
with the cloud model, 'real' stays local. This module only *carries* `kind`; the invariant that no
`real` engagement ever reaches the cloud is enforced in the model router (R7.4), not here.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone

_VALID_KINDS = {"practice", "real"}
_VALID_MODES = {"white"}  # v1: loud white-box only; Red-stealth is a later slice.


class ConfigError(ValueError):
    """engagement.toml is missing a required field or holds an invalid value."""


@dataclass(frozen=True)
class ModelConfig:
    analysis: str
    reasoner_cloud: str
    reasoner_local: str
    cve_source: str


@dataclass(frozen=True)
class ReconConfig:
    tool_timeout_secs: int
    nmap_args: str


@dataclass(frozen=True)
class Engagement:
    id: str
    target: str
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    mode: str
    kind: str
    models: ModelConfig
    recon: ReconConfig
    created_at: str


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "engagement"


def stable_engagement_id(target: str, in_scope, out_of_scope) -> str:
    """Deterministic id from target + scope.

    Re-running the *same* engagement.toml resumes the *same* engagement (idempotency, R5.3) rather
    than forking a new one. `created_at` deliberately does not feed the id.
    """
    payload = json.dumps(
        {"t": target, "in": sorted(in_scope), "out": sorted(out_of_scope)},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha1(payload.encode()).hexdigest()[:8]
    return f"{_slug(target)}-{digest}"


def _require_str(section: dict, key: str, where: str) -> str:
    val = section.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ConfigError(f"[{where}] requires a non-empty string '{key}'")
    return val.strip()


def _str_list(section: dict, key: str, where: str, *, required: bool) -> tuple[str, ...]:
    val = section.get(key)
    if val is None:
        if required:
            raise ConfigError(f"[{where}] requires '{key}' (a non-empty list)")
        return ()
    if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
        raise ConfigError(f"[{where}] '{key}' must be a list of strings")
    cleaned = tuple(x.strip() for x in val if x.strip())
    if required and not cleaned:
        raise ConfigError(f"[{where}] '{key}' must contain at least one entry")
    return cleaned


def load_engagement(path: str) -> Engagement:
    """Load and validate engagement.toml. Raises ConfigError on any invalid/missing field."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)

    eng = data.get("engagement")
    if not isinstance(eng, dict):
        raise ConfigError("missing [engagement] section")

    target = _require_str(eng, "target", "engagement")
    in_scope = _str_list(eng, "in_scope", "engagement", required=True)  # R1.1
    out_of_scope = _str_list(eng, "out_of_scope", "engagement", required=False)

    mode = str(eng.get("mode", "white")).strip().lower()
    if mode not in _VALID_MODES:
        raise ConfigError(f"engagement.mode must be one of {sorted(_VALID_MODES)} in v1 (got '{mode}')")

    kind = str(eng.get("kind", "")).strip().lower()
    if kind not in _VALID_KINDS:
        raise ConfigError(f"engagement.kind must be one of {sorted(_VALID_KINDS)} (got '{kind}')")

    models_raw = data.get("models")
    if not isinstance(models_raw, dict):
        raise ConfigError("missing [models] section")
    models = ModelConfig(
        analysis=_require_str(models_raw, "analysis", "models"),
        reasoner_cloud=_require_str(models_raw, "reasoner_cloud", "models"),
        reasoner_local=_require_str(models_raw, "reasoner_local", "models"),
        cve_source=_require_str(models_raw, "cve_source", "models"),
    )

    recon_raw = data.get("recon", {})
    if not isinstance(recon_raw, dict):
        raise ConfigError("[recon] must be a table")
    timeout = recon_raw.get("tool_timeout_secs", 300)
    if not isinstance(timeout, int) or timeout <= 0:
        raise ConfigError("recon.tool_timeout_secs must be a positive integer")
    recon = ReconConfig(
        tool_timeout_secs=timeout,
        nmap_args=str(recon_raw.get("nmap_args", "-sV -T4")),
    )

    explicit_id = eng.get("id")
    engagement_id = (
        str(explicit_id).strip()
        if isinstance(explicit_id, str) and explicit_id.strip()
        else stable_engagement_id(target, in_scope, out_of_scope)
    )

    return Engagement(
        id=engagement_id,
        target=target,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        mode=mode,
        kind=kind,
        models=models,
        recon=recon,
        created_at=_utcnow_iso(),
    )
