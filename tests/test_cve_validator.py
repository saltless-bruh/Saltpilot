"""Milestone 5 — the deterministic CVE validator, the CVE-fabrication slice-blocking fix (Task 5.0,
R4.2). Model proposes, validator disposes."""

from __future__ import annotations

from pathlib import Path

from saltpilot.interpret import CveVerdict, build_cve_validator

SEED = str(Path(__file__).parent / "fixtures" / "cve_seed.json")


def _v():
    return build_cve_validator(SEED)


def test_real_cve_right_product_is_valid():
    assert _v().validate("CVE-2014-0160", "OpenSSL", "1.0.1") is CveVerdict.VALID


def test_existence_only_when_no_product_given():
    assert _v().validate("CVE-2014-0160", None, None) is CveVerdict.VALID


def test_made_up_id_is_not_found():
    assert _v().validate("CVE-9999-9999", "openssl", None) is CveVerdict.NOT_FOUND


def test_malformed_id_is_not_found():
    assert _v().validate("not-a-cve", "openssl", None) is CveVerdict.NOT_FOUND
    assert _v().validate("CVE-XX", "openssl", None) is CveVerdict.NOT_FOUND


def test_real_id_wrong_product_is_mismatch():
    # CVE-2014-0160 is OpenSSL; asserting it against nginx must be flagged, not stored.
    assert _v().validate("CVE-2014-0160", "nginx", None) is CveVerdict.MISMATCH


def test_case_insensitive_product_and_id():
    assert _v().validate("cve-2014-6271", "GNU Bash", None) is CveVerdict.VALID


def test_version_out_of_range_is_mismatch():
    # CVE-2099-0001 affects acme-widget 1.0/1.1 only.
    assert _v().validate("CVE-2099-0001", "acme-widget", "2.0") is CveVerdict.MISMATCH
    assert _v().validate("CVE-2099-0001", "acme-widget", "1.0") is CveVerdict.VALID


def test_empty_source_drops_everything_failsafe(monkeypatch):
    # No mirror configured -> everything NOT_FOUND, so no model-asserted CVE can ever be persisted.
    monkeypatch.delenv("SALTPILOT_CVE_DB", raising=False)
    v = build_cve_validator("nvd_local")  # unresolved -> EmptyCveSource
    assert v.validate("CVE-2014-0160", "openssl", None) is CveVerdict.NOT_FOUND
