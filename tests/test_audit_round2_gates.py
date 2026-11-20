"""Test regresi audit putaran 2 — gates/sandbox/coverage (N1, N4, N7, N11)
+ ruff --fix di sandbox (Rendah).

Setiap test di sini mereproduksi PoC laporan audit
``AUDIT-AI-AGENT-PUTARAN-2-2026-11-20.md`` dan HARUS lulus sebelum
temuan dianggap selesai:

- N1: runner palsu ``exit 2, stdout ""`` -> semua gate
  ``passed=False`` (``rule="tool-error"`` untuk tool JSON/lint),
  verdict != AMAN. Exit code tiap tool diperiksa; output kosong /
  rusak -> gagal, bukan [].
- N4: coverage ditulis ke mount di luar worktree (``/out``);
  ``coverage.json`` palsu 100% di worktree diabaikan; perubahan
  ``conftest.py`` / ``pytest.ini`` / ``pyproject [tool.pytest]``
  tanpa review manusia (= belum di-commit) = blocking.
- N7: ``docker_available()`` True HANYA bila daemon merespons
  ``docker info`` DAN image ada — binary saja tidak cukup. Test
  memakai mock (``subprocess.run``), bukan ``shutil.which``.
- N11: ``interrupt()`` sebelum code (approve_spec, sudah ada) dan
  sebelum commit (approve_commit, baru) — resume True lanjut,
  resume False menolak.
- Ruff ``--fix`` di node revise jalan di sandbox, bukan di host.
"""

from __future__ import annotations

import asyncio
import json
import subprocess

import pytest

from mufakat.gates import bandit as bandit_gate
from mufakat.gates import gitleaks as gitleaks_gate
from mufakat.gates import lint as lint_gate
from mufakat.gates import pytest as pytest_gate
from mufakat.gates import semgrep as semgrep_gate
from mufakat.gates import trivy as trivy_gate
from mufakat.gates.runner import GateResult, run_all
from mufakat.gates.verdict import verdict
from tests.test_gates import GOOD_APP, GOOD_TEST, fake_sandbox_runner

APP_SEBAGIAN = '''"""App dengan satu fungsi yang tidak pernah dipanggil test."""


def used(x):
    return x + 1


def unused():
    return 99
'''

TEST_SEBAGIAN = '''"""Test hanya memanggil used()."""

from app import used


def test_used():
    assert used(1) == 2
'''


def _write(path, name, content):
    (path / name).write_text(content, encoding="utf-8")


def _runner_for(exit_code, stdout="", stderr=""):
    """Fake sandbox runner yang selalu mengembalikan hasil tetap."""
    def _runner(image, workdir, command, timeout=300, network_none=True,
                read_only=False, **kwargs):
        return {"exit_code": exit_code, "stdout": stdout,
                "stderr": stderr, "sandbox_unavailable": False}
    return _runner


def _crashing_runner(image, workdir, command, timeout=300, network_none=True,
                     read_only=False, **kwargs):
    """PoC N1: tool crash (exit 2, stdout kosong)."""
    return {"exit_code": 2, "stdout": "", "stderr": "tool crash",
            "sandbox_unavailable": False}


def _tool_error(result):
    return any(f.get("rule") == "tool-error" for f in result.findings)


# ---------------------------------------------------------------------------
# N1 — exit code + output kosong/rusak
# ---------------------------------------------------------------------------
def test_n1_runner_crash_semua_gate_gagal_verdict_bukan_aman(tmp_path):
    """PoC N1: runner palsu exit 2 stdout "" -> semua gate gagal."""
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    results = run_all(tmp_path, sandbox_runner=_crashing_runner)
    assert len(results) == 6
    assert all(r.passed is False for r in results)
    by_tool = {r.tool: r for r in results}
    for tool in ("semgrep", "bandit", "gitleaks", "trivy", "lint"):
        assert _tool_error(by_tool[tool]), tool
    out = verdict(results)
    assert out["safe"] is False
    assert out["status"] != "AMAN"
    assert out["status"] == "BELUM_TERVERIFIKASI"


@pytest.mark.parametrize("exit_code,stdout", [
    (2, ""), (3, ""), (124, ""),
    (0, ""),  # bersih tapi tanpa output JSON
    (0, "bukan-json"), (1, "{rusak"),
])
def test_n1_semgrep_exit_dan_output_tak_valid_gagal(tmp_path, exit_code, stdout):
    _write(tmp_path, "app.py", GOOD_APP)
    result = semgrep_gate.run(
        tmp_path, sandbox_runner=_runner_for(exit_code, stdout))
    assert result.passed is False
    assert _tool_error(result)


def test_n1_semgrep_exit_1_dengan_temuan_tetap_dibaca(tmp_path):
    """Exit 1 (--error) + JSON valid = temuan dibaca, bukan tool-error."""
    payload = json.dumps({"results": [{
        "path": "app.py", "start": {"line": 3}, "check_id": "x",
        "extra": {"severity": "ERROR", "message": "buruk"}}]})
    result = semgrep_gate.run(tmp_path, sandbox_runner=_runner_for(1, payload))
    assert result.passed is False
    assert not _tool_error(result)
    assert result.findings[0]["severity"] == "HIGH"


@pytest.mark.parametrize("exit_code,stdout", [
    (2, ""), (0, ""), (0, "bukan-json"), (1, "{rusak"),
])
def test_n1_bandit_output_rusak_bukan_nol_temuan(tmp_path, exit_code, stdout):
    _write(tmp_path, "app.py", GOOD_APP)
    result = bandit_gate.run(
        tmp_path, sandbox_runner=_runner_for(exit_code, stdout))
    assert result.passed is False
    assert _tool_error(result)


def test_n1_bandit_json_valid_tetap_dibaca(tmp_path):
    payload = json.dumps({"results": [{
        "test_id": "B307", "filename": "app.py", "line_number": 1,
        "issue_severity": "HIGH", "issue_text": "eval"}]})
    result = bandit_gate.run(tmp_path, sandbox_runner=_runner_for(1, payload))
    assert result.passed is False
    assert not _tool_error(result)


@pytest.mark.parametrize("exit_code,stdout,expected_passed,expected_tool_error", [
    (0, "", True, False),      # gitleaks tanpa temuan memang tanpa output
    (1, "", False, True),      # exit 1 tapi output kosong = tak valid
    (2, "", False, True),
    (0, "bukan-json", False, True),
    (1, json.dumps([{"File": "a.py", "StartLine": 1, "RuleID": "x",
                     "Description": "secret"}]), False, False),
])
def test_n1_gitleaks_exit_dan_output(tmp_path, exit_code, stdout,
                                    expected_passed, expected_tool_error):
    _write(tmp_path, "app.py", GOOD_APP)
    result = gitleaks_gate.run(
        tmp_path, sandbox_runner=_runner_for(exit_code, stdout))
    assert result.passed is expected_passed
    assert _tool_error(result) is expected_tool_error


@pytest.mark.parametrize("exit_code,stdout", [
    (1, ""), (2, ""), (0, ""), (0, "bukan-json"),
])
def test_n1_trivy_exit_dan_output_tak_valid_gagal(tmp_path, exit_code, stdout):
    _write(tmp_path, "app.py", GOOD_APP)
    result = trivy_gate.run(
        tmp_path, sandbox_runner=_runner_for(exit_code, stdout))
    assert result.passed is False
    assert _tool_error(result)


def test_n1_trivy_exit_0_json_valid_tetap_dibaca(tmp_path):
    payload = json.dumps({"Results": []})
    result = trivy_gate.run(tmp_path, sandbox_runner=_runner_for(0, payload))
    assert result.passed is True


def test_n1_lint_exit_2_adalah_tool_error_bukan_temuan(tmp_path):
    _write(tmp_path, "app.py", GOOD_APP)
    result = lint_gate.run(tmp_path, sandbox_runner=_runner_for(2, ""))
    assert result.passed is False
    assert _tool_error(result)


def test_n1_lint_exit_1_output_kosong_adalah_tool_error(tmp_path):
    _write(tmp_path, "app.py", GOOD_APP)
    result = lint_gate.run(tmp_path, sandbox_runner=_runner_for(1, ""))
    assert result.passed is False
    assert _tool_error(result)


def test_n1_pytest_exit_3_adalah_tool_error(tmp_path):
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    result = pytest_gate.run(tmp_path, sandbox_runner=_runner_for(3, "INTERNALERROR"))
    assert result.passed is False
    assert _tool_error(result)


def test_n1_verdict_tool_error_belum_terverifikasi():
    out = verdict([GateResult(tool="semgrep", passed=False, findings=[{
        "severity": "HIGH", "file": "", "line": 0,
        "rule": "tool-error", "message": "crash"}])])
    assert out["status"] == "BELUM_TERVERIFIKASI"
    assert out["safe"] is False


# ---------------------------------------------------------------------------
# N4 — coverage di luar worktree + config pytest = blocking
# ---------------------------------------------------------------------------
def test_n4_coverage_ditulis_di_luar_worktree_dan_nyata(tmp_path):
    """PoC N4: coverage.json palsu 100% di worktree diabaikan.

    Fake 100% ditanam dulu; coverage nyata < 100% (fungsi unused()
    tidak dipanggil). Gate harus membaca nilai NYATA dari mount
    luar, dan tidak meninggalkan coverage.json di worktree.
    """
    _write(tmp_path, "app.py", APP_SEBAGIAN)
    _write(tmp_path, "test_app.py", TEST_SEBAGIAN)
    _write(tmp_path, "coverage.json",
           json.dumps({"totals": {"percent_covered": 100}}))
    result = pytest_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is True
    assert result.coverage is not None
    assert result.coverage < 1.0  # nilai nyata, bukan palsu 100%
    assert result.coverage > 0.5
    assert not (tmp_path / "coverage.json").exists()
    assert not (tmp_path / ".coverage").exists()
    assert not (tmp_path / ".pytest_cache").exists()


def test_n4_conftest_tanpa_review_adalah_blocking(tmp_path):
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    _write(tmp_path, "conftest.py", '"""Conftest buatan AI."""\n')
    result = pytest_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is False
    assert any(f["rule"] == "pytest-config-changed" for f in result.findings)
    out = verdict([result])
    assert out["status"] != "AMAN"


def test_n4_pyproject_tool_pytest_tanpa_review_adalah_blocking(tmp_path):
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    _write(tmp_path, "pyproject.toml",
           "[tool.pytest.ini_options]\naddopts = \"-p no:cov\"\n")
    result = pytest_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is False
    assert any(f["rule"] == "pytest-config-changed" for f in result.findings)


def test_n4_pyproject_tanpa_tool_pytest_tidak_blocking(tmp_path):
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    _write(tmp_path, "pyproject.toml", "[project]\nname = \"contoh\"\n")
    result = pytest_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is True


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def test_n4_conftest_yang_sudah_dicommit_tidak_blocking(tmp_path):
    """File config yang SUDAH di-commit (= melewati review) dipercaya."""
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    _write(tmp_path, "conftest.py", '"""Conftest yang sudah direview."""\n')
    _git("init", "-q", cwd=tmp_path)
    _git("add", "-A", cwd=tmp_path)
    _git("-c", "user.email=t@t.t", "-c", "user.name=Tes",
         "commit", "-qm", "awal", cwd=tmp_path)
    result = pytest_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is True
    assert not any(f["rule"] == "pytest-config-changed"
                   for f in result.findings)


def test_n4_conftest_diubah_setelah_commit_jadi_blocking(tmp_path):
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    _write(tmp_path, "conftest.py", '"""v1."""\n')
    _git("init", "-q", cwd=tmp_path)
    _git("add", "-A", cwd=tmp_path)
    _git("-c", "user.email=t@t.t", "-c", "user.name=Tes",
         "commit", "-qm", "awal", cwd=tmp_path)
    _write(tmp_path, "conftest.py",
           '"""v2 jahat: matikan cov."""\nimport pytest\n')
    result = pytest_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is False
    assert any(f["rule"] == "pytest-config-changed" for f in result.findings)


# ---------------------------------------------------------------------------
# N7 — deteksi daemon + image (mock, bukan shutil.which)
# ---------------------------------------------------------------------------
def _mock_docker_subprocess(monkeypatch, info_ok, inspect_ok):
    """Mock subprocess.run di mufakat.sandbox.docker.

    Binary "ada" (which -> path); daemon/image mengikuti argumen.
    """
    import mufakat.sandbox.docker as docker_mod

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker")

    def _fake_run(args, **kwargs):
        cmd = list(args)
        if cmd[:2] == ["docker", "info"]:
            rc = 0 if info_ok else 1
        elif cmd[:3] == ["docker", "image", "inspect"]:
            rc = 0 if inspect_ok else 1
        else:  # pragma: no cover - tidak dipakai test ini
            rc = 0
        return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="")

    monkeypatch.setattr(docker_mod.subprocess, "run", _fake_run)


def test_n7_cli_tanpa_daemon_tidak_tersedia(monkeypatch):
    """PoC N7: binary ada, `docker info` gagal -> docker_available False."""
    _mock_docker_subprocess(monkeypatch, info_ok=False, inspect_ok=False)
    from mufakat.sandbox import docker as docker_mod

    assert docker_mod.docker_daemon_available() is False
    assert docker_mod.docker_available() is False


def test_n7_daemon_hidup_tapi_image_tidak_ada_tidak_tersedia(monkeypatch):
    _mock_docker_subprocess(monkeypatch, info_ok=True, inspect_ok=False)
    from mufakat.sandbox import docker as docker_mod

    assert docker_mod.docker_daemon_available() is True
    assert docker_mod.docker_image_available() is False
    assert docker_mod.docker_available() is False


def test_n7_daemon_dan_image_ada_tersedia(monkeypatch):
    _mock_docker_subprocess(monkeypatch, info_ok=True, inspect_ok=True)
    from mufakat.sandbox import docker as docker_mod

    assert docker_mod.docker_available() is True


def test_n7_binary_tidak_ada_tidak_tersedia(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    from mufakat.sandbox import docker as docker_mod

    assert docker_mod.docker_available() is False


def test_n7_run_in_sandbox_daemon_mati_belum_terverifikasi(monkeypatch):
    """Daemon mati -> run_in_sandbox sandbox_unavailable (tanpa docker run)."""
    _mock_docker_subprocess(monkeypatch, info_ok=False, inspect_ok=False)
    from mufakat.sandbox import docker as docker_mod

    result = docker_mod.run_in_sandbox("mufakat-sandbox", "/tmp", "echo hi")
    assert result["sandbox_unavailable"] is True
    assert result["exit_code"] == 127


# ---------------------------------------------------------------------------
# N11 — interrupt sebelum code (spec) dan sebelum commit (revise)
# ---------------------------------------------------------------------------
def test_n11_build_graph_param_require_human_approval(tmp_path):
    """Parameter baru build_graph mengaktifkan interrupt spec."""
    from langgraph.types import Command

    from mufakat.graph.build import build_graph

    graph = build_graph(adapters={}, require_human_approval=True)
    state = {"run_id": "t1", "idea": "ide tes", "provider": "mock",
             "run_dir": str(tmp_path)}
    cfg = {"configurable": {"thread_id": "n11-param"}}
    first = asyncio.run(graph.ainvoke(state, cfg))
    assert "__interrupt__" in first
    assert first["__interrupt__"][0].value["type"] == "approve_spec"
    resumed = asyncio.run(graph.ainvoke(Command(resume=True), cfg))
    assert resumed.get("approved_spec") is True


def _mini_revise_graph():
    """Graph minimal berisi HANYA node revise (untuk uji interrupt)."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    from mufakat.graph.nodes.revise import node as revise_node
    from mufakat.graph.state import RunState

    graph = StateGraph(RunState)
    shared = {"require_human_approval": True}

    async def _revise(state):
        return await revise_node(state, {}, shared)

    graph.add_node("revise", _revise)
    graph.add_edge(START, "revise")
    graph.add_edge("revise", END)
    return graph.compile(checkpointer=MemorySaver())


def test_n11_interrupt_sebelum_commit_disetujui(tmp_path):
    """Tanpa temuan + HITL: jeda approve_commit, resume True -> commit."""
    from langgraph.types import Command

    graph = _mini_revise_graph()
    cfg = {"configurable": {"thread_id": "n11-commit-ok"}}
    state = {"run_id": "t1", "idea": "ide", "provider": "mock",
             "run_dir": str(tmp_path), "findings": []}
    first = asyncio.run(graph.ainvoke(state, cfg))
    assert "__interrupt__" in first
    assert first["__interrupt__"][0].value["type"] == "approve_commit"
    resumed = asyncio.run(graph.ainvoke(Command(resume=True), cfg))
    assert resumed.get("approved_commit") is True
    assert resumed.get("status") == "done"


def test_n11_interrupt_sebelum_commit_ditolak(tmp_path):
    """Resume False -> commit DITOLAK (approved_commit False, blocked)."""
    from langgraph.types import Command

    graph = _mini_revise_graph()
    cfg = {"configurable": {"thread_id": "n11-commit-no"}}
    state = {"run_id": "t1", "idea": "ide", "provider": "mock",
             "run_dir": str(tmp_path), "findings": []}
    first = asyncio.run(graph.ainvoke(state, cfg))
    assert "__interrupt__" in first
    resumed = asyncio.run(graph.ainvoke(Command(resume=False), cfg))
    assert resumed.get("approved_commit") is False
    assert resumed.get("status") == "blocked"


# ---------------------------------------------------------------------------
# Ruff --fix di sandbox (Rendah)
# ---------------------------------------------------------------------------
def test_ruff_fix_jalan_di_sandbox_bukan_host(tmp_path):
    """Node revise memanggil sandbox runner (ruff --fix), bukan host."""
    from mufakat.graph.nodes.revise import node as revise_node
    from mufakat.graph.state import RunState

    calls: list[dict] = []

    def _fake_sandbox(image, workdir, command, timeout=120,
                      network_none=True, read_only=False, **kwargs):
        calls.append({"image": image, "workdir": workdir,
                      "command": command, "read_only": read_only})
        return {"exit_code": 0, "stdout": "", "stderr": "",
                "sandbox_unavailable": False}

    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / "app.py").write_text("x=1\n", encoding="utf-8")
    state = RunState(run_id="t1", idea="ide",
                     findings=[{"severity": "MEDIUM", "rule": "E225"}])
    patch = asyncio.run(revise_node(
        state, adapters={},
        ctx={"worktree": str(worktree), "sandbox_runner": _fake_sandbox}))
    assert len(calls) == 1
    assert "ruff check --fix" in calls[0]["command"]
    assert calls[0]["read_only"] is False  # --fix butuh tulis
    assert calls[0]["workdir"] == str(worktree)
    assert patch["phase"] == "review"


def test_ruff_fix_tanpa_docker_tidak_jalan_di_host(tmp_path, monkeypatch):
    """Tanpa Docker: ruff --fix TIDAK dijalankan (host maupun sandbox).

    Bukti: subprocess.run dimock agar meledak bila dipanggil — node
    harus tetap selesai dengan fixed=False tanpa memanggilnya.
    """
    from mufakat.graph.nodes.revise import node as revise_node
    from mufakat.graph.state import RunState

    def _no_subprocess(*args, **kwargs):
        raise AssertionError("ruff --fix tidak boleh jalan di host")

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / "app.py").write_text("x=1\n", encoding="utf-8")
    state = RunState(run_id="t1", idea="ide",
                     findings=[{"severity": "MEDIUM", "rule": "E225"}])
    patch = asyncio.run(revise_node(
        state, adapters={}, ctx={"worktree": str(worktree)}))
    assert patch["phase"] == "review"
    assert "tidak dijalankan/gagal" in patch["messages"][-1]["content"]
