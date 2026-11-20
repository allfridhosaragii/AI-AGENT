"""Demo mock end-to-end MUFAKAT Room (tanpa situs AI asli).

Menjalankan alur manual handoff lengkap dengan jawaban PALSU (mock)
yang disimulasikan sebagai hasil impor pengguna:

1. Buat Room, susun prompt proposal untuk 3 provider.
2. Simulasi pengguna: salin prompt -> kirim di tab resmi -> impor jawaban.
3. Hitung konsensus Borda (reuse ``mufakat.consensus.voting``).
4. Jalankan gates nyata (reuse ``mufakat.gates.runner``) atas kode contoh
   kecil, lalu verdict (reuse ``mufakat.gates.verdict``).
5. Tulis laporan ke ``runs/room-mock-<id>/final_report.md``.

Jalankan: ``.venv/bin/python -m mufakat.room.demo "Ide ..."``
Tidak ada yang dikirim ke situs AI mana pun dalam demo ini.
"""

from __future__ import annotations

import json
import secrets
import sys
import tempfile
from pathlib import Path

from mufakat.room.handoff import Room
from mufakat.room.pacing import PacingLedger

MOCK_REPLIES = {
    "chatgpt": (
        "Usulan: bangun REST API todo dengan FastAPI + SQLite, test pytest.\n"
        "```json\n"
        '{"phase": "proposal", "summary": "FastAPI + SQLite, CRUD todo, test pytest.",'
        ' "proposal": "FastAPI + SQLite",'
        ' "vote": {"decision": "approve", "ranking": ["A", "B", "C"], "confidence": 0.8}}\n'
        "```"
    ),
    "claude": (
        "Usulan: FastAPI dengan lapisan repository agar mudah diuji.\n"
        "```json\n"
        '{"phase": "proposal", "summary": "FastAPI berlapis repository, mudah diuji.",'
        ' "proposal": "FastAPI berlapis",'
        ' "vote": {"decision": "approve", "ranking": ["A", "C", "B"], "confidence": 0.75}}\n'
        "```"
    ),
    "gemini": (
        "Usulan: FastAPI + Pydantic, dokumentasi OpenAPI otomatis.\n"
        "```json\n"
        '{"phase": "proposal", "summary": "FastAPI + Pydantic, OpenAPI otomatis.",'
        ' "proposal": "FastAPI + Pydantic",'
        ' "vote": {"decision": "approve", "ranking": ["B", "A", "C"], "confidence": 0.7}}\n'
        "```"
    ),
}

SAMPLE_CODE = (
    '"""Contoh kode hasil AI (mock) untuk gate demo."""\n\n\n'
    "def add(a: int, b: int) -> int:\n"
    '    """Jumlahkan dua bilangan."""\n'
    "    return a + b\n"
)

SAMPLE_TEST = (
    '"""Test contoh."""\n\nfrom sample import add\n\n\n'
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
)


def run_mock_demo(idea: str, output_dir: str | Path | None = None) -> dict:
    """Jalankan demo mock; kembalikan ringkasan + tulis laporan."""
    from mufakat.gates.runner import run_all
    from mufakat.gates.verdict import verdict as gate_verdict

    run_id = secrets.token_hex(4)
    base = Path(output_dir) if output_dir else Path("runs") / f"room-mock-{run_id}"
    base.mkdir(parents=True, exist_ok=True)

    ledger = PacingLedger(path=base / "usage.json")
    room = Room(
        room_id=f"room-mock-{run_id}",
        idea=idea,
        providers=["chatgpt", "claude", "gemini"],
        room_dir=base / "room",
        pacing_ledger=ledger,
    )
    room.build_prompts(template="proposal", role="debater")
    imported = []
    for provider_id in room.providers:
        room.copy_prompt(provider_id)  # pengguna menyalin (simulasi aksi sadar)
        room.mark_submitted(provider_id)
        record = room.import_response(provider_id, MOCK_REPLIES[provider_id])
        imported.append(record)
    consensus = room.consensus()
    room.transition("finalize")

    # Gates nyata atas kode contoh (reuse gates MUFAKAT yang sudah ada).
    with tempfile.TemporaryDirectory(prefix="mufakat-room-gates-") as tmp:
        sample_dir = Path(tmp)
        (sample_dir / "sample.py").write_text(SAMPLE_CODE, encoding="utf-8")
        (sample_dir / "test_sample.py").write_text(SAMPLE_TEST, encoding="utf-8")
        gate_results = run_all(sample_dir)
        gate_verdict_result = gate_verdict(gate_results)

    report_lines = [
        "# Laporan Mock MUFAKAT Room (end-to-end, jawaban palsu)",
        "",
        f"Room: {room.room_id}",
        f"Ide: {idea}",
        f"State akhir: {room.state} | Ronde: {room.round_no}",
        "Mode: manual_handoff (default) — tidak ada yang dikirim otomatis ke situs AI.",
        "",
        "## Provider",
        "",
    ]
    for status in room.provider_statuses():
        report_lines.append(
            f"- {status['name']} ({status['official_url']}): {status['status_label']}"
        )
    report_lines += [
        "",
        "## Respons yang diimpor (user imported)",
        "",
    ]
    for record in imported:
        report_lines.append(
            f"- {record['provider']}: parse={record['parse_status']}, "
            f"vote={(record.get('parsed') or {}).get('vote')}"
        )
    report_lines += [
        "",
        "## Konsensus (Borda, reuse mufakat.consensus.voting)",
        "",
        "```json",
        json.dumps(consensus, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Gates (reuse mufakat.gates.runner atas kode contoh)",
        "",
    ]
    for result in gate_results:
        report_lines.append(f"- {result.tool}: passed={result.passed}")
    report_lines += [
        "",
        f"Verdict gates: **{gate_verdict_result['status']}** — {gate_verdict_result['summary']}",
        "",
        "## Catatan jujur",
        "",
        "- Jawaban di atas adalah MOCK (palsu), bukan dari situs AI asli.",
        "- Langkah manual yang disimulasikan di sini (salin prompt, kirim di tab "
        "resmi, salin jawaban, impor) pada pemakaian nyata dilakukan pengguna.",
        "- Docker sandbox belum terverifikasi di VM ini; gates di atas jalan "
        "langsung (bukan di container).",
        "",
    ]
    report = "\n".join(report_lines)
    (base / "final_report.md").write_text(report, encoding="utf-8")
    summary = {
        "room_id": room.room_id,
        "dir": str(base),
        "state": room.state,
        "consensus": consensus,
        "gate_verdict": gate_verdict_result["status"],
        "gates": {r.tool: r.passed for r in gate_results},
        "report": str(base / "final_report.md"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    idea = args[0] if args else "Buat REST API todo dengan FastAPI + test + audit"
    run_mock_demo(idea)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
