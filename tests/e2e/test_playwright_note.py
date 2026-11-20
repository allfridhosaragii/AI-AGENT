"""Catatan Playwright untuk E2E MUFAKAT.

Playwright TIDAK terpasang di VM ini (tidak ada binary browser
dan paket ``playwright`` tidak ada di .venv). Karena itu E2E
dashboard diuji lewat HTTP TestClient (lihat
test_dashboard_e2e.py), bukan lewat browser sungguhan.

Test ini mendokumentasikan status itu secara eksplisit: bila
Playwright suatu hari terpasang, test ini memberi tahu bahwa
E2E browser bisa ditambahkan — sampai saat itu, statusnya adalah
"belum terpasang", bukan "lolos".
"""

from __future__ import annotations

import pytest


def test_playwright_status_didokumentasikan():
    try:
        import playwright  # noqa: F401
    except ImportError:
        pytest.skip(
            "Playwright belum terpasang di VM ini — E2E memakai "
            "TestClient (HTTP), bukan browser sungguhan.")
    pytest.skip(
        "Playwright terpasang, tetapi E2E browser belum ditulis — "
        "E2E saat ini memakai TestClient (HTTP).")
