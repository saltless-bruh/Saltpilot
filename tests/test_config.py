"""Milestone 0 — engagement.toml loading and validation (Task 0.3, R1/R7)."""

from __future__ import annotations

import textwrap

import pytest

from saltpilot.config import ConfigError, Engagement, load_engagement

VALID = """
[engagement]
target = "lab.internal"
in_scope = ["lab.internal", "10.10.10.0/24"]
out_of_scope = ["10.10.10.1"]
mode = "white"
kind = "practice"

[models]
analysis        = "foundation-sec-8b-reasoning"
reasoner_cloud  = "deepseek-v4-flash"
reasoner_local  = "qwen3-4b-thinking-2507"
cve_source      = "nvd_local"

[recon]
tool_timeout_secs = 300
nmap_args = "-sV -T4"
"""


def _write(tmp_path, body: str):
    p = tmp_path / "engagement.toml"
    p.write_text(textwrap.dedent(body))
    return str(p)


def test_loads_valid_config(tmp_path):
    e = load_engagement(_write(tmp_path, VALID))
    assert isinstance(e, Engagement)
    assert e.target == "lab.internal"
    assert e.in_scope == ("lab.internal", "10.10.10.0/24")
    assert e.out_of_scope == ("10.10.10.1",)
    assert e.kind == "practice"
    assert e.mode == "white"
    assert e.models.analysis == "foundation-sec-8b-reasoning"
    assert e.models.reasoner_local == "qwen3-4b-thinking-2507"
    assert e.recon.tool_timeout_secs == 300


def test_id_is_stable_across_loads(tmp_path):
    # Same config -> same engagement id, so a re-run resumes rather than forks (idempotency).
    e1 = load_engagement(_write(tmp_path, VALID))
    e2 = load_engagement(_write(tmp_path, VALID))
    assert e1.id == e2.id
    assert e1.created_at is not None


def test_scope_change_changes_id(tmp_path):
    e1 = load_engagement(_write(tmp_path, VALID))
    e2 = load_engagement(_write(tmp_path, VALID.replace('"10.10.10.1"', '"10.10.10.2"')))
    assert e1.id != e2.id


def test_explicit_id_is_respected(tmp_path):
    body = VALID.replace('[engagement]\n', '[engagement]\nid = "fixed-engagement-007"\n')
    assert load_engagement(_write(tmp_path, body)).id == "fixed-engagement-007"


def test_missing_target_raises(tmp_path):
    body = VALID.replace('target = "lab.internal"\n', "")
    with pytest.raises(ConfigError):
        load_engagement(_write(tmp_path, body))


def test_empty_in_scope_raises(tmp_path):
    body = VALID.replace('in_scope = ["lab.internal", "10.10.10.0/24"]', "in_scope = []")
    with pytest.raises(ConfigError):
        load_engagement(_write(tmp_path, body))


def test_invalid_kind_raises(tmp_path):
    body = VALID.replace('kind = "practice"', 'kind = "production"')
    with pytest.raises(ConfigError):
        load_engagement(_write(tmp_path, body))


def test_non_white_mode_raises_in_v1(tmp_path):
    body = VALID.replace('mode = "white"', 'mode = "red"')
    with pytest.raises(ConfigError):
        load_engagement(_write(tmp_path, body))


def test_out_of_scope_optional(tmp_path):
    body = VALID.replace('out_of_scope = ["10.10.10.1"]\n', "")
    e = load_engagement(_write(tmp_path, body))
    assert e.out_of_scope == ()
