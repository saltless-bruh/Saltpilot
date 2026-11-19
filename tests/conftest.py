from __future__ import annotations

import textwrap

import pytest

from saltpilot.config import load_engagement


def _write_engagement(
    tmp_path,
    *,
    target="127.0.0.1",
    in_scope=("127.0.0.1",),
    out_of_scope=(),
    nmap_args="-sV -T4",
    kind="practice",
):
    body = f"""
    [engagement]
    target = "{target}"
    in_scope = {list(in_scope)!r}
    out_of_scope = {list(out_of_scope)!r}
    mode = "white"
    kind = "{kind}"

    [models]
    analysis = "foundation-sec-8b-reasoning"
    reasoner_cloud = "deepseek-v4-flash"
    reasoner_local = "qwen3-4b-thinking-2507"
    cve_source = "nvd_local"

    [recon]
    tool_timeout_secs = 120
    nmap_args = "{nmap_args}"
    """
    path = tmp_path / "engagement.toml"
    path.write_text(textwrap.dedent(body))
    return load_engagement(str(path))


@pytest.fixture
def make_engagement():
    """Return a factory that writes an engagement.toml and loads it into an Engagement."""
    return _write_engagement
