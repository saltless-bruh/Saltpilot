"""Milestone 2 — a live Checkpoint-2 run: real nmap against a throwaway localhost service.

127.0.0.1 is my own container — always authorized. Skipped automatically where nmap is absent, so
the rest of the suite stays hermetic. This is the real (not simulated) proof that the pipeline
runs a tool, persists correct services, and re-runs idempotently.
"""

from __future__ import annotations

import functools
import http.server
import shutil
import threading
from pathlib import Path

import pytest

from saltpilot.recon import build_network_recon
from saltpilot.store import GraphStore

pytestmark = pytest.mark.skipif(shutil.which("nmap") is None, reason="nmap not installed")


def _counts(store: GraphStore) -> tuple[int, int]:
    with store.connect() as con:
        assets = con.execute("SELECT count(*) FROM asset").fetchone()[0]
        findings = con.execute("SELECT count(*) FROM finding").fetchone()[0]
    return assets, findings


def test_live_recon_against_localhost(make_engagement, tmp_path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
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
