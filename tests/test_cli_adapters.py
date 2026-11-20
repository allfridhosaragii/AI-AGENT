"""Test gating adapter CLI MUFAKAT.

Aturan (ditemukan 20 Nov 2026): `load_from_config` mengembalikan
adapter CLI hanya karena entrinya ada di providers.yaml — tetapi
`codex` di VM ini TIDAK login (`codex login status` = "Not logged
in"). Menjalankan CLI yang belum login menggantung graph tanpa
batas (menunggu input interaktif). Karena itu `_build_adapters`
HANYA memakai adapter CLI bila `is_available()` (login
terverifikasi); bila tidak, peran memakai mock deterministik.
`run_cli` juga tidak pernah mewarisi stdin (DEVNULL).
"""

from __future__ import annotations

import asyncio
import time

import pytest

from mufakat.adapters._cli import run_cli
from mufakat.runner import _build_adapters


class _State:
    idea = "ide tes"


def test_build_adapters_memakai_mock_bila_cli_belum_login(monkeypatch):
    # Hermetis (H4): hasil test tidak boleh bergantung pada binary CLI
    # yang kebetulan terpasang di host — mock shutil.which supaya
    # semua CLI dianggap tidak tersedia.
    import shutil

    from mufakat.adapters import _cli as cli_mod

    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(cli_mod.shutil, "which", lambda name: None)
    adapters = _build_adapters()
    text = asyncio.run(adapters["research"](_State()))
    # Mock research: teks lokal, bukan jawaban CLI/API.
    assert "dihasilkan secara lokal" in text
    review = asyncio.run(adapters["review"](_State()))
    # Teks mock review TIDAK BOLEH mengandung kata "blocking"
    # (node review memakai kata itu sebagai penanda temuan).
    assert "blocking" not in review.lower()


def test_run_cli_tidak_menggantung_pada_stdin():
    # `cat` membaca stdin sampai EOF; dengan stdin DEVNULL ia
    # langsung selesai. Bila stdin diwariskan dari proses induk,
    # test ini akan menggantung (timeout pytest).
    started = time.monotonic()
    reply = asyncio.run(run_cli("test", "test", ["cat"], None))
    assert time.monotonic() - started < 10
    assert reply.text == ""


def test_run_cli_gagal_bila_binary_tidak_ada():
    from mufakat.adapters.base import AdapterError

    with pytest.raises(AdapterError):
        asyncio.run(run_cli("test", "test",
                            ["perintah-yang-tidak-ada-xyz"], None))
