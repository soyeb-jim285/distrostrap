"""Version discovery for the Fedora plugin."""

from __future__ import annotations

import subprocess

from distrostrap.distros import fedora

_LISTING = '<a href="42/">42/</a> <a href="43/">43/</a> <a href="44/">44/</a>'


def _fake_curl(stdout: str, returncode: int = 0):
    def run(cmd, **kwargs):
        # The listing must come from the master mirror; the redirector
        # 404s on directory indexes.
        assert cmd[-1].startswith("https://dl.fedoraproject.org/")
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")

    return run


def test_fetch_returns_newest_first(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_curl(_LISTING))
    assert fedora._fetch_fedora_variants() == ["44", "43", "42"]


def test_fetch_falls_back_when_listing_unavailable(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_curl("", returncode=22))
    assert fedora._fetch_fedora_variants() == fedora._FALLBACK_VARIANTS
