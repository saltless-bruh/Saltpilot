"""Milestone 6 — the deterministic grounding guard, the slice-blocking fix (Task 6.2b, R6.2)."""

from __future__ import annotations

from saltpilot.findings import Fact
from saltpilot.query import ground_guard


def _facts():
    return [
        Fact("asset:1", "asset", "host 10.10.10.7", hosts=("10.10.10.7",)),
        Fact("finding:1", "finding", "nginx on 10.10.10.7:8899", hosts=("10.10.10.7",), ports=(8899,)),
        Fact("asset:2", "asset", "web endpoint admin.acme.com", hosts=("admin.acme.com",)),
        Fact("interp:1", "interpretation", "nginx host", hosts=("10.10.10.7",), cves=("CVE-2014-0160",)),
    ]


def test_fully_grounded_answer_passes_clean():
    ans = "Host 10.10.10.7 runs nginx on port 8899 [finding:1]; likely CVE-2014-0160 [interp:1]."
    checked, flagged = ground_guard(ans, _facts())
    assert flagged == []
    assert checked == ans  # nothing altered


def test_invented_ip_is_flagged_and_marked():
    checked, flagged = ground_guard("Also 10.9.9.9 looks vulnerable.", _facts())
    assert flagged == ["10.9.9.9"]
    assert "[unverified: 10.9.9.9]" in checked


def test_invented_cve_is_flagged():
    checked, flagged = ground_guard("This is affected by CVE-2021-99999.", _facts())
    assert flagged == ["CVE-2021-99999"]
    assert "[unverified: CVE-2021-99999]" in checked


def test_invented_port_is_flagged():
    checked, flagged = ground_guard("There is also a database on port 3306.", _facts())
    assert flagged == ["3306"]
    assert "[unverified: 3306]" in checked


def test_invented_hostname_is_flagged_but_known_one_passes():
    checked, flagged = ground_guard("admin.acme.com is exposed; so is evil.example.org.", _facts())
    assert flagged == ["evil.example.org"]
    assert "admin.acme.com" in checked and "[unverified: evil.example.org]" in checked


def test_citation_ids_are_not_mistaken_for_ports():
    # '[finding:12]' / '[asset:3]' must not be flagged as invented ports 12 / 3.
    checked, flagged = ground_guard("See [finding:12] and [asset:3] for details on 10.10.10.7.", _facts())
    assert flagged == []


def test_known_port_and_cve_pass():
    checked, flagged = ground_guard("Port 8899 is open; CVE-2014-0160 applies.", _facts())
    assert flagged == []
