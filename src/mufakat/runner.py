"""Inti pipeline MUFAKAT — logika bersama CLI, MCP, dan Web.

Hanya memakai standard library, supaya modul ini bisa diimpor tanpa
dependensi berat. Percobaan memakai LangGraph (bila tersedia) dilakukan
di dalam fungsi dan selalu punya fallback penulisan langsung — pipeline
tidak boleh gagal total hanya karena graph belum ada.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

RUNS_ENV_VAR = "MUFAKAT_RUNS_DIR"
DEFAULT_OUTPUT = "runs"


def utcnow() -> str:
    """Waktu UTC dalam format ISO 8601."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    """ID run pendek (8 karakter heksadesimal)."""
    return uuid.uuid4().hex[:8]


def runs_dir(output: str | None = None) -> Path:
    """Folder runs: argumen > env MUFAKAT_RUNS_DIR > ./runs."""
    base = output or os.environ.get(RUNS_ENV_VAR) or DEFAULT_OUTPUT
    return Path(base)


def mufakat_message(
    run_id: str,
    *,
    round_no: int = 1,
    phase: str = "proposal",
    agent_id: str = "moderator",
    role: str = "moderator",
    model_family: str = "other",
    summary: str = "",
    proposal: str = "",
    provider: str = "mock",
) -> dict:
    """Satu baris MufakatMessage (sesuai JSON Schema §8 dokumen arsitektur)."""
    return {
        "run_id": run_id,
        "round": round_no,
        "phase": phase,
        "agent_id": agent_id,
        "role": role,
        "model_family": model_family,
        "stance": "neutral",
        "content": {
            "summary": summary[:1200],
            "proposal": proposal,
            "claims": [],
            "critiques": [],
            "vote": {"decision": "approve", "ranking": [agent_id], "confidence": 0.0},
        },
        "usage": {"provider": provider, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
        "timestamp": utcnow(),
    }


def _write_graph_artifacts(run_id: str, run_dir: Path, idea: str,
                           provider: str, mode: str, state: dict) -> None:
    """Tulis artefak dari state akhir graph LangGraph (bukan mock)."""
    messages = state.get("messages") or []
    spec_text = state.get("spec") or f"# Spesifikasi — run `{run_id}`\n\nIde: {idea}\n"
    lines = []
    for i, m in enumerate(messages):
        role = str(m.get("role", "debater"))
        content = str(m.get("content", ""))
        phase = {"researcher": "research", "debater": "proposal",
                 "moderator": "meeting", "spec": "spec"}.get(role, "proposal")
        lines.append(json.dumps(mufakat_message(
            run_id, round_no=1, phase=phase, agent_id=role, role=role,
            model_family="other", summary=content[:1200],
            proposal=content if role == "debater" else "", provider=provider,
        ), ensure_ascii=False))
    if not lines:
        lines.append(json.dumps(mufakat_message(
            run_id, phase="spec", summary=f"Graph selesai: {idea[:200]}",
            proposal=idea, provider=provider), ensure_ascii=False))
    (run_dir / "transcript.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run_dir / "rounds" / "round-01.md").write_text(
        "# Ronde 01 — Debat (LangGraph)\n\n"
        f"Ide/topik: {idea}\n\nProvider: {provider} | Mode: {mode} | Run: `{run_id}`\n\n"
        f"Jumlah pesan: {len(messages)} | Fase akhir: {state.get('phase', '')}\n\n"
        + "\n".join(
            f"- **{m.get('role', '?')}**: {str(m.get('content', ''))[:300]}"
            for m in messages
        ),
        encoding="utf-8",
    )
    (run_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (run_dir / "final_report.md").write_text(
        f"# Laporan Akhir — run `{run_id}`\n\n"
        f"Ide/topik: {idea}\n\n"
        f"Provider: {provider} | Mode: {mode} | Graph: LangGraph dipakai\n\n"
        "## Status\n\n"
        f"Selesai via graph LangGraph (fase akhir: {state.get('phase', '')}, "
        f"{len(messages)} pesan debat). Ini run mock (tanpa provider AI nyata) — "
        "hasil debat berasal dari node dummy deterministik.\n\n"
        "## Batasan jujur\n\n"
        "- Gate dijalankan atas worktree setelah graph selesai — "
        "lihat bagian Gate & Diff di bawah laporan ini.\n"
        "- Jangan klaim hasil ini 100% aman.\n",
        encoding="utf-8",
    )


def _try_graph_run(idea: str, provider: str, run_dir: Path, run_id: str,
                   mode: str = "run") -> bool:
    """Jalankan graph LangGraph bila tersedia; tulis artefaknya.

    Graph dipanggil dengan adapter (API nyata bila ada key di env,
    mock bila tidak) dan ctx bersama berisi ``worktree`` +
    ``run_dir`` — node code menulis file nyata ke worktree, node
    audit/test menjalankan gate atas file itu.

    Mengembalikan True bila graph berhasil dipakai, False bila tidak ada
    atau gagal — pemanggil lalu memakai fallback penulisan langsung.
    """
    try:
        from mufakat.graph import build_graph
    except Exception:
        return False
    if build_graph is None:
        return False
    try:
        import asyncio

        worktree = run_dir / "worktree"
        worktree.mkdir(parents=True, exist_ok=True)
        adapters = _build_adapters()
        ctx = {"worktree": str(worktree), "run_dir": str(run_dir)}
        graph = build_graph(adapters=adapters, ctx=ctx)
        state_in = {"run_id": run_id, "idea": idea, "provider": provider,
                    "run_dir": str(run_dir)}
        # Node graph bersifat async -> pakai ainvoke (invoke sinkron
        # LangGraph menolak node async).
        if hasattr(graph, "ainvoke"):
            result = asyncio.run(graph.ainvoke(
                state_in, {"configurable": {"thread_id": run_id}}))
        else:
            result = graph.invoke(state_in)
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        elif hasattr(result, "model_dump"):
            result = result.model_dump()
        if not isinstance(result, dict):
            return False
        _write_graph_artifacts(run_id, run_dir, idea, provider, mode, result)
        return True
    except Exception:
        return False


def _build_adapters() -> dict:
    """Bangun dict adapter untuk node graph.

    Bila ada API key / CLI di env (``config/providers.yaml``),
    adapter nyata dipakai — node memanggil model sungguhan lewat
    ``Adapter.ask``. Bila tidak ada, dipakai mock deterministik
    yang mengembalikan teks/template lokal (dan dicatat sebagai
    mock di pesan node). Tidak pernah membaca kredensial CLI
    provider lain; key hanya dibaca dari env oleh
    ``load_from_config``.
    """
    from mufakat.graph.nodes.code import TEMPLATE_MAIN

    real: dict = {}
    try:
        from pathlib import Path as _Path

        from mufakat.adapters.api_openai_compat import load_from_config

        config_path = _Path(__file__).resolve().parents[2] / "config" / "providers.yaml"
        if config_path.is_file():
            real = load_from_config(config_path)
    except Exception:
        real = {}

    # Adapter CLI (codex/copilot/antigravity/claude/opencode) hanya
    # dipakai bila login-nya TERVERIFIK lewat ``is_available()``
    # (probe `login status`, maks. 5 detik, stdin DEVNULL). Tanpa
    # login terverifikasi, adapter CLI DIABAIKAN dan peran memakai
    # mock deterministik — jangan pernah menjalankan CLI yang belum
    # login: CLI akan menggantung menunggu input interaktif dan
    # mengunci graph (ditemukan 20 Nov 2026: `codex` ada di PATH
    # tetapi `codex login status` = "Not logged in").
    cli_names = {"codex", "copilot", "antigravity", "claude", "opencode"}
    usable: dict = {}
    for _name, _adapter in real.items():
        if _name in cli_names:
            try:
                if _adapter.is_available():
                    usable[_name] = _adapter
            except Exception:
                continue
        else:
            usable[_name] = _adapter
    real = usable

    def _real_fn(adapter, role: str):
        async def _fn(state):
            idea = getattr(state, "idea", "")
            reply = await adapter.ask(
                f"{role}\n\nIde/topik: {idea}\n\n"
                "Jawab singkat, konkret, dan dalam Bahasa Indonesia.",
                system=f"Kamu adalah {role} dalam sistem MUFAKAT.",
                ctx={"timeout": 120})
            return reply.text
        return _fn

    def _mock_fn(text_fn):
        async def _fn(state):
            return text_fn(getattr(state, "idea", ""))
        return _fn

    adapters: dict = {}
    # Debat: satu adapter per agen (deepseek/openrouter/gemini).
    for agent in ("deepseek", "openrouter", "gemini"):
        if agent in real:
            adapters[f"debate_{agent}"] = _real_fn(
                real[agent], f"debater {agent} (stance: pro/kontra/netral)")
        else:
            adapters[f"debate_{agent}"] = _mock_fn(
                lambda idea, agent=agent: (
                    f"Proposal {agent}: bangun solusi untuk '{idea}' dengan "
                    f"pendekatan {agent} — sederhana, teruji, dan mudah dirawat."))

    # Peran lain: pakai adapter nyata pertama bila ada (urutan rantai
    # debat), bila tidak mock deterministik.
    first_real = None
    for name in ("deepseek", "openrouter", "groq", "gemini",
                 "meta_api", "codex", "copilot", "antigravity", "claude",
                 "opencode"):
        if name in real:
            first_real = real[name]
            break
    adapters["research"] = (
        _real_fn(first_real, "researcher") if first_real else _mock_fn(
            lambda idea: (
                f"Riset awal untuk ide: '{idea}'. Temuan: (1) kebutuhan utama "
                "pengguna perlu dipetakan; (2) ada pendekatan sederhana yang "
                "sudah umum dipakai; (3) risiko utama adalah ruang lingkup "
                "yang melebar. Riset ini dihasilkan secara lokal tanpa "
                "memanggil API.")))
    adapters["critique"] = (
        _real_fn(first_real, "kritikus") if first_real else _mock_fn(
            lambda idea: (
                "Kritik: (1) Proposal A paling sederhana tetapi kurang "
                "menangani kasus pinggir; (2) Proposal B paling lengkap "
                "tetapi paling mahal; (3) Proposal C seimbang, namun perlu "
                "penegasan ruang lingkup. Tidak ada kritik blocking; "
                "rekomendasi: lanjutkan Proposal C dengan penyederhanaan "
                "dari Proposal A.")))
    adapters["spec"] = (
        _real_fn(first_real, "arsitek (tulis spesifikasi)") if first_real
        else _mock_fn(lambda idea: (
            "# Spesifikasi (spec.md)\n\n"
            f"## Ide\n{idea}\n\n"
            "## Tujuan\nMembangun solusi yang sederhana, teruji, dan mudah "
            "dirawat sesuai hasil mufakat debat.\n\n"
            "## Kriteria Penerimaan\n"
            "- Semua gate verifikasi lolos.\n"
            "- Review menyetujui dengan rasio minimal 2/3.\n")))
    adapters["review"] = (
        _real_fn(first_real, "code reviewer independen") if first_real
        else _mock_fn(lambda idea: "Review: tidak ada temuan."))
    adapters["revise"] = (
        _real_fn(first_real, "reviser kode") if first_real else _mock_fn(
            lambda idea: "Revisi: perbaiki temuan dengan ruff --fix."))
    adapters["code"] = (
        _real_fn(first_real,
                 "coder: tulis implementasi REST API todo FastAPI "
                 "(main.py lengkap, kode Python saja dalam blok ```python)")
        if first_real else _mock_fn(lambda idea: TEMPLATE_MAIN))
    adapters["_real_provider"] = (
        getattr(first_real, "name", "") if first_real else "mock")
    return adapters


def _finalize_worktree(run_dir: Path) -> dict:
    """Tulis diff + hasil gate nyata atas worktree run.

    Mengembalikan ringkasan ``{"diff": ..., "verdict": ..., "gates": [...]}``.
    Bila worktree kosong/tidak ada, kembalikan status
    ``belum terverifikasi`` yang jujur — bukan klaim lolos.
    """
    import difflib

    worktree = run_dir / "worktree"
    summary: dict = {"diff": None, "verdict": None, "gates": []}
    if not worktree.is_dir():
        return summary
    files = sorted(p for p in worktree.iterdir() if p.is_file())
    if not files:
        return summary
    diff_dir = run_dir / "diff"
    diff_dir.mkdir(parents=True, exist_ok=True)
    patch_lines: list[str] = []
    for path in files:
        content = path.read_text(encoding="utf-8").splitlines(keepends=True)
        patch_lines.extend(difflib.unified_diff(
            [], content, fromfile="/dev/null", tofile=path.name))
    patch_path = diff_dir / "iter-01.patch"
    patch_path.write_text("".join(patch_lines), encoding="utf-8")
    summary["diff"] = str(patch_path)
    gates_dir = run_dir / "gates"
    gates_dir.mkdir(parents=True, exist_ok=True)
    try:
        from mufakat.gates.runner import run_all
        from mufakat.gates.verdict import verdict as gate_verdict

        results = run_all(worktree)
        for result in results:
            record = {"tool": result.tool, "passed": bool(result.passed),
                      "findings": list(getattr(result, "findings", []) or [])}
            (gates_dir / f"{result.tool}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8")
            summary["gates"].append(record)
        verdict_result = gate_verdict(results)
        (gates_dir / "verdict.json").write_text(
            json.dumps(verdict_result, ensure_ascii=False, indent=2),
            encoding="utf-8")
        summary["verdict"] = verdict_result
    except Exception as exc:  # noqa: BLE001 — gate gagal = belum terverifikasi
        summary["verdict"] = {"safe": False, "status": "belum terverifikasi",
                              "summary": f"Gate tidak dapat dijalankan: {exc}",
                              "categories": []}
    report_path = run_dir / "final_report.md"
    if report_path.is_file():
        verdict_text = summary["verdict"] or {}
        gate_lines = "\n".join(
            f"- {g['tool']}: {'lolos' if g['passed'] else 'GAGAL'} "
            f"({len(g['findings'])} temuan)"
            for g in summary["gates"])
        report_path.write_text(
            report_path.read_text(encoding="utf-8")
            + "\n## Gate & Diff (nyata, dijalankan atas worktree)\n\n"
            f"Verdict: **{verdict_text.get('status', 'belum terverifikasi')}** — "
            f"{verdict_text.get('summary', '')}\n\n"
            f"{gate_lines}\n\n"
            f"Diff: `{summary['diff']}`\n"
            f"Worktree: `{worktree}`\n",
            encoding="utf-8")
    return summary


def _write_mock_artifacts(
    run_id: str, run_dir: Path, idea: str, provider: str, mode: str
) -> None:
    """Tulis artefak run mock: transcript.jsonl, round-01.md, spec, laporan.

    Memakai :class:`MufakatMessage` + ``TranscriptWriter`` bila tersedia,
    dan jatuh kembali ke dict JSON standar bila tidak.
    """
    phase = "spec" if mode == "debate" else "proposal"
    summary = f"Mode {mode} (provider {provider}, mock): {idea[:200]}"
    content = {
        "summary": summary[:1200],
        "proposal": idea,
        "claims": [],
        "critiques": [],
        "vote": {"decision": "approve", "ranking": ["moderator"], "confidence": 0.0},
        "usage": {"provider": provider, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
    }
    try:
        from mufakat.consensus.protocol import (  # type: ignore
            ModelFamily,
            MufakatMessage,
            Phase,
            Role,
            to_jsonl,
        )

        line = to_jsonl(
            MufakatMessage(
                run_id=run_id,
                round=1,
                phase=Phase(phase),
                agent_id="moderator",
                role=Role.MODERATOR,
                model_family=ModelFamily.OTHER,
                content=content,
            )
        )
    except Exception:
        line = json.dumps(
            mufakat_message(
                run_id,
                round_no=1,
                phase=phase,
                summary=summary,
                proposal=idea,
                provider=provider,
            ),
            ensure_ascii=False,
        )
    with open(run_dir / "transcript.jsonl", "w", encoding="utf-8") as fh:
        fh.write(line + "\n")

    (run_dir / "rounds" / "round-01.md").write_text(
        "# Ronde 01 — Proposal (mock)\n\n"
        f"Ide/topik: {idea}\n\n"
        f"Provider: {provider} | Mode: {mode} | Run: `{run_id}`\n\n"
        "## Vote\n\n"
        "| Agen | Peran | Keputusan | Keyakinan |\n"
        "|------|-------|-----------|-----------|\n"
        "| moderator | moderator | approve | 0.00 |\n\n"
        "## Kritik\n\n"
        "Belum ada kritik — ini run mock. Debat multi-provider asli "
        "memerlukan provider yang terhubung (lihat README & DECISIONS.md).\n",
        encoding="utf-8",
    )

    (run_dir / "spec.md").write_text(
        f"# Spesifikasi — run `{run_id}`\n\n"
        f"**Ide/topik:** {idea}\n\n"
        f"**Provider:** {provider} | **Mode:** {mode}\n\n"
        "## Ringkasan\n\n"
        "Spesifikasi awal hasil run mock MUFAKAT. Ganti isi ini dengan "
        "hasil debat nyata setelah provider debat dipilih dan dihubungkan.\n\n"
        "## Persyaratan\n\n"
        "- [ ] Persyaratan fungsional diturunkan dari hasil debat.\n"
        "- [ ] Risiko / dissent dicatat bila debat tidak mencapai mufakat.\n"
        "- [ ] Gate keamanan & pengujian lolos sebelum merge.\n",
        encoding="utf-8",
    )

    (run_dir / "final_report.md").write_text(
        f"# Laporan Akhir — run `{run_id}`\n\n"
        f"Ide/topik: {idea}\n\n"
        f"Provider: {provider} | Mode: {mode} | Graph LangGraph: "
        "tidak tersedia — fallback langsung\n\n"
        "## Status\n\n"
        "Selesai (mock). Belum ada gate yang terverifikasi — lihat "
        "`gate_report` di MCP atau jalankan pengujian & pemindai keamanan.\n",
        encoding="utf-8",
    )


def create_run(
    idea: str,
    provider: str = "mock",
    output: str | None = None,
    mode: str = "run",
) -> dict:
    """Buat satu run: folder runs/<id>/ + transcript, ronde, spec, laporan.

    mode: "run" (pipeline penuh, mock), "debate" (debat saja),
    "pipeline" (dari spec/repo).
    """
    run_id = new_run_id()
    base = runs_dir(output)
    run_dir = base / run_id
    (run_dir / "rounds").mkdir(parents=True, exist_ok=True)
    (run_dir / "gates").mkdir(parents=True, exist_ok=True)

    used_graph = _try_graph_run(idea, provider, run_dir, run_id, mode)

    if not used_graph:
        _write_mock_artifacts(run_id, run_dir, idea, provider, mode)

    # Diff + gate nyata atas worktree (bila ada file yang dihasilkan).
    finalize = _finalize_worktree(run_dir)

    status = {
        "run_id": run_id,
        "idea": idea,
        "provider": provider,
        "mode": mode,
        "status": "completed",
        "graph_used": used_graph,
        "created_at": utcnow(),
        "dir": str(run_dir),
        "diff": finalize.get("diff"),
        "verdict": (finalize.get("verdict") or {}).get("status"),
        "gates": [
            {"tool": g["tool"], "passed": g["passed"],
             "findings": len(g["findings"])}
            for g in finalize.get("gates", [])
        ],
    }
    (run_dir / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return status


def read_run(run_id: str, output: str | None = None) -> dict | None:
    """Baca satu run dari runs/<run_id>/. None bila tidak ditemukan.

    M12: ``run_id`` tidak valid (mis. ``".."``) langsung None — tidak
    boleh membaca folder di luar ``runs/``.
    """
    try:
        from mufakat.sandbox.worktree import validate_run_id

        validate_run_id(run_id)
    except (ValueError, ImportError):
        return None
    run_dir = runs_dir(output) / run_id
    if not run_dir.is_dir():
        return None
    status_path = run_dir / "status.json"
    status = {}
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            status = {}
    transcript_path = run_dir / "transcript.jsonl"
    messages: list[dict] = []
    if transcript_path.is_file():
        for line in transcript_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    files = sorted(p.name for p in run_dir.iterdir()) if run_dir.is_dir() else []
    return {
        "run_id": run_id,
        "status": status.get("status", "unknown"),
        "idea": status.get("idea", ""),
        "provider": status.get("provider", "mock"),
        "mode": status.get("mode", "run"),
        "created_at": status.get("created_at", ""),
        "dir": str(run_dir),
        "files": files,
        "message_count": len(messages),
        "messages": messages,
        "has_spec": (run_dir / "spec.md").exists(),
        "has_final_report": (run_dir / "final_report.md").exists(),
    }


def list_runs(output: str | None = None) -> list[dict]:
    """Daftar run di folder runs/, terbaru dulu."""
    base = runs_dir(output)
    if not base.is_dir():
        return []
    runs: list[dict] = []
    for child in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir():
            continue
        info = read_run(child.name, output)
        if info is not None:
            info.pop("messages", None)
            runs.append(info)
    return runs


def load_sqlite_table(db_path: str | Path, table: str) -> list[dict]:
    """Baca satu tabel SQLite bila file & tabelnya ada; else list kosong."""
    db_path = Path(db_path)
    if not db_path.is_file():
        return []
    # Validasi identifier: nama tabel hanya boleh [A-Za-z_][A-Za-z0-9_]*.
    # Nama tabel tidak bisa diparameterisasi di SQLite, jadi validasi
    # ketat + pengecekan keberadaan di sqlite_master adalah mitigasinya.
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if cur.fetchone() is None:
                return []
            cur = conn.execute(
                f'SELECT * FROM "{table}"'  # nosec B608 - identifier sudah divalidasi regex + sqlite_master
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return []


def find_sqlite_db(output: str | None = None) -> Path | None:
    """Cari file SQLite di folder runs/ (mufakat.db / mufakat.sqlite)."""
    base = runs_dir(output)
    for name in ("mufakat.db", "mufakat.sqlite", "mufakat.sqlite3"):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None
