"""Live Checkpoint-2/3 runs: real nmap (and real ProjectDiscovery httpx) against a throwaway
localhost service.

127.0.0.1 is my own container — always authorized. Skipped automatically where the tools are
absent, so the rest of the suite stays hermetic. This is the real (not simulated) proof that the
pipeline runs tools, persists correct findings, and re-runs idempotently.
"""

from __future__ import annotations

import functools
import http.server
import os
import shutil
import subprocess
import threading

import pytest

from saltpilot.recon import build_network_recon, build_recon
from saltpilot.store import GraphStore

pytestmark = pytest.mark.skipif(shutil.which("nmap") is None, reason="nmap not installed")


def _counts(store: GraphStore) -> tuple[int, int]:
    with store.connect() as con:
        assets = con.execute("SELECT count(*) FROM asset").fetchone()[0]
        findings = con.execute("SELECT count(*) FROM finding").fetchone()[0]
    return assets, findings


def _find_pd_httpx() -> str | None:
    """Locate a ProjectDiscovery httpx binary (the name may be shadowed by the Python httpx CLI)."""
    for candidate in ("/opt/pd-bin/httpx", os.path.expanduser("~/go/bin/httpx"), shutil.which("httpx")):
        if not candidate:
            continue
        try:
            out = subprocess.run([candidate, "-version"], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        if "projectdiscovery" in f"{out.stdout}\n{out.stderr}".lower():
            return candidate
    return None


def _serve(tmp_path, body: str = "<html><body>hi</body></html>"):
    (tmp_path / "index.html").write_text(body)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def test_live_recon_against_localhost(make_engagement, tmp_path):
    server, port = _serve(tmp_path)
    try:
        eng = make_engagement(tmp_path, nmap_args=f"-sV -p {port} -T4")
        store = GraphStore(str(tmp_path / "live.sqlite"))
        store.init_schema()
        runner = build_network_recon(eng, store)  # real executor + real nmap

        result = runner.run()
        assert any(f.port == port for f in result.findings), result.coverage

        before = _counts(store)
        runner.run()  # idempotent re-run
        assert _counts(store) == before
    finally:
        server.shutdown()
        server.server_close()


def test_live_network_then_web(make_engagement, tmp_path):
    """Checkpoint 3: nmap finds the web port, httpx enriches it (title/status), all persisted."""
    httpx_bin = _find_pd_httpx()
    if httpx_bin is None:
        pytest.skip("ProjectDiscovery httpx not found")

    server, port = _serve(tmp_path, "<html><head><title>Live Lab</title></head><body>hi</body></html>")
    try:
        eng = make_engagement(tmp_path, nmap_args=f"-sV -p {port} -T4")
        store = GraphStore(str(tmp_path / "live_web.sqlite"))
        store.init_schema()
        runner = build_recon(eng, store, httpx_binary=httpx_bin)  # real nmap + real PD httpx

        result = runner.run()
        web = [f for f in result.findings if f.kind == "web_endpoint" and f.port == port]
        assert web, result.coverage
        assert web[0].detail["status_code"] == 200
        assert "Live Lab" in (web[0].detail.get("title") or "")

        before = _counts(store)
        runner.run()  # idempotent re-run of the full two-stage pipeline
        assert _counts(store) == before
    finally:
        server.shutdown()
        server.server_close()
