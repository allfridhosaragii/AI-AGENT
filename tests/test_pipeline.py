"""Test pipeline nyata MUFAKAT: code -> review -> audit -> test.

Satu run mock end-to-end harus menulis, bukan hanya teks ringkasan:
- worktree/main.py + worktree/test_main.py (kode nyata),
- diff/iter-01.patch (unified diff),
- gates/<tool>.json untuk tiap gate + gates/verdict.json,
- status.json dengan verdict AMAN untuk template yang bersih.
"""

from __future__ import annotations

import asyncio
import json

from mufakat.graph.nodes.code import node as code_node_fn
from mufakat.graph.nodes.review import node as review_node_fn
from mufakat.graph.nodes.revise import node as revise_node_fn
from mufakat.graph.state import RunState
from mufakat.runner import create_run, read_run


def test_code_node_menulis_file_nyata(tmp_path):
    worktree = tmp_path / "wt"
    state = RunState(run_id="t1", idea="Buat REST API todo dengan FastAPI")
    patch = asyncio.run(code_node_fn(state, adapters={}, ctx={"worktree": str(worktree)}))
    assert (worktree / "main.py").is_file()
    assert (worktree / "test_main.py").is_file()
    assert "FastAPI" in (worktree / "main.py").read_text(encoding="utf-8")
    assert patch["diff_hash"]
    assert patch["phase"] == "review"


def test_review_node_tanpa_blocking(tmp_path):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / "main.py").write_text("x = 1\n", encoding="utf-8")
    state = RunState(run_id="t1", idea="ide")
    patch = asyncio.run(review_node_fn(state, adapters={},
                                        ctx={"worktree": str(worktree)}))
    assert patch["phase"] == "audit"
    assert not [f for f in patch["findings"] if f.get("severity") == "blocking"]


def test_revise_node_tanpa_temuan_selesai():
    state = RunState(run_id="t1", idea="ide", findings=[])
    patch = asyncio.run(revise_node_fn(state, adapters={}, ctx={}))
    assert patch["status"] == "done"
    assert patch["approved_commit"] is True


def test_create_run_menulis_diff_dan_gates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = create_run("Buat REST API todo dengan FastAPI + test + audit",
                        output="runs")
    run_dir = tmp_path / "runs" / result["run_id"]
    assert (run_dir / "worktree" / "main.py").is_file()
    assert (run_dir / "worktree" / "test_main.py").is_file()
    patch = run_dir / "diff" / "iter-01.patch"
    assert patch.is_file()
    assert "main.py" in patch.read_text(encoding="utf-8")
    verdict_path = run_dir / "gates" / "verdict.json"
    assert verdict_path.is_file()
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["status"] == "AMAN"
    for tool in ("semgrep", "bandit", "gitleaks", "pytest", "lint"):
        gate_file = run_dir / "gates" / f"{tool}.json"
        assert gate_file.is_file(), tool
        record = json.loads(gate_file.read_text(encoding="utf-8"))
        assert record["passed"] is True, tool
    assert result["verdict"] == "AMAN"
    assert result["diff"] is not None
    info = read_run(result["run_id"])
    assert info is not None
