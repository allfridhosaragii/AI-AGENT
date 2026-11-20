"""Test end-to-end dashboard web MUFAKAT (HTTP, TestClient/httpx).

Alur penuh yang diuji: health -> buat debat via POST -> baca
detail run (termasuk diff + verdict gate nyata) -> daftar run ->
endpoint pendukung. Playwright TIDAK dipakai di sini karena
tidak terpasang di VM — lihat test_playwright_note.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mufakat.web.app import app


def test_e2e_dashboard_alur_penuh(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    created = client.post(
        "/api/debate",
        json={"topic": "Buat REST API todo dengan FastAPI + test + audit"})
    assert created.status_code == 201
    body = created.json()
    run_id = body["run_id"]
    # Run nyata menulis diff + verdict gate (bukan hanya ringkasan).
    assert body["verdict"] == "AMAN"
    assert body["diff"] is not None
    assert any(g["tool"] == "pytest" and g["passed"] for g in body["gates"])

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run_id
    assert detail.json()["message_count"] >= 1

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    assert runs.json()["count"] == 1

    for path in ("/api/projects", "/api/meetings", "/api/tasks",
                 "/api/approvals", "/api/usage", "/api/audit"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.json()["status"] == "ok"

    assert client.get("/api/runs/tidakada").status_code == 404
    assert client.get("/").status_code == 200
    assert "MUFAKAT" in client.get("/").text


def test_e2e_debate_tanpa_topik_ditolak(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    res = client.post("/api/debate", json={"topic": ""})
    assert res.status_code == 422
