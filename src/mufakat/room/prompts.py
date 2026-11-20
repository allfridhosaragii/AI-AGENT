"""Template prompt MUFAKAT Room (Claude §T4, §3).

Satu template per peran & fase. Semua template diakhiri instruksi blok
`````json`` agar jawaban bisa diparse (lihat :mod:`mufakat.room.parser`).
Placeholder: ``{idea}``, ``{context}``, ``{role}``, ``{round_no}``,
``{disputes}``, ``{findings}``.

Template ini dipakai untuk menyusun prompt manual handoff — prompt
disalin pengguna ke tab resmi provider, BUKAN dikirim otomatis.
"""

from __future__ import annotations

__all__ = ["PROMPT_TEMPLATES", "render_prompt", "JSON_FOOTER"]

JSON_FOOTER = (
    "\n\nTulis penjelasan singkat, lalu akhiri dengan SATU blok ```json sesuai skema "
    "berikut (jangan ada blok json lain sesudahnya):\n"
    "```json\n"
    '{\n  "phase": "<proposal|critique|meeting|spec|code|review|audit|test|revise>",\n'
    '  "summary": "ringkasan maks 1200 karakter",\n'
    '  "proposal": "isi usulan (fase proposal/rebuttal)",\n'
    '  "claims": [{"id": "c1", "text": "...", "evidence": "...",\n'
    '    "confidence": 0.8}],\n'
    '  "critiques": [{"target": "B", "claim": "c2", "severity": "major",\n'
    '    "text": "..."}],\n'
    '  "vote": {"decision": "approve|revise|reject",\n'
    '    "ranking": ["A", "C", "B"], "confidence": 0.7},\n'
    '  "files": [{"path": "src/app.py", "mode": "replace|patch",\n'
    '    "content": "isi file atau unified diff"}]\n'
    "}\n```"
)

PROMPT_TEMPLATES: dict[str, str] = {
    "proposal": (
        "Kamu adalah {role} dalam rapat multi-AI. Ide yang dibahas:\n{idea}\n\n"
        "Konteks:\n{context}\n\n"
        "Buat usulan solusi yang konkret dan mandiri. Jangan melihat usulan AI lain "
        "(kamu belum diberi akses ke sana). Sertakan asumsi, risiko, dan langkah "
        "implementasi singkat."
    ),
    "critique": (
        "Kamu adalah {role} (kritikus). Berikut usulan-usulan yang sudah dianonimkan "
        "dengan label A/B/C (nama AI disembunyikan):\n{context}\n\n"
        "Beri kritik spesifik untuk setiap usulan: kutip bagian yang dipersoalkan, "
        "beri severity info|minor|major|blocking, lalu ranking semua usulan dari "
        "terbaik ke terburuk."
    ),
    "meeting": (
        "Kamu adalah moderator rapat. Ringkasan ronde sebelumnya:\n{context}\n\n"
        "Buat rangkuman mufakat: usulan teratas, daftar perselisihan yang belum "
        "selesai, dan keputusan (approve/revise/reject) beserta alasannya. "
        "Catat pendapat minoritas (dissent) bila ada."
    ),
    "rebuttal": (
        "Kamu adalah {role}. Daftar perselisihan yang belum selesai:\n{disputes}\n\n"
        "Jawab tiap kritik: terima, tolak dengan alasan, atau minta data tambahan. "
        "Jangan membahas hal di luar daftar perselisihan ini (hemat kuota)."
    ),
    "spec": (
        "Kamu adalah {role}. Tulis spesifikasi teknis dari hasil rapat berikut:\n"
        "{context}\n\nSpesifikasi harus mencakup: tujuan, requirement fungsional dan "
        "non-fungsional, arsitektur singkat, struktur file, kriteria penerimaan, "
        "dan risiko/dissent yang tercatat."
    ),
    "code": (
        "Kamu adalah coder. Implementasikan spesifikasi berikut:\n{context}\n\n"
        "Kirim file utuh (mode replace) atau unified diff (mode patch) pada blok "
        "json. Kode harus bisa di-test; jangan sertakan kredensial atau rahasia."
    ),
    "review": (
        "Kamu adalah reviewer (keluarga AI berbeda dari coder). Review kode berikut:\n"
        "{context}\n\nPeriksa: kebenaran, keamanan, kualitas, dan test. Beri kritik "
        "dengan severity info|minor|major|blocking dan vote approve|revise|reject."
    ),
    "audit": (
        "Kamu adalah security auditor. Audit kode berikut:\n{context}\n\n"
        "Cari: injeksi, kebocoran secret, otorisasi yang hilang, dan dependensi "
        "berisiko. Hasil tool deterministik (test/scanner) adalah hakim akhir, "
        "bukan opinimu."
    ),
    "test": (
        "Kamu adalah tester. Tulis test untuk kode berikut:\n{context}\n\n"
        "Test harus mencakup kasus normal, kasus batas, dan kasus gagal. "
        "Target coverage kode baru minimal 80%."
    ),
    "revise": (
        "Kamu adalah coder. Perbaiki kode berdasarkan temuan berikut:\n{findings}\n\n"
        "Konteks kode:\n{context}\n\nKirim file/diff yang sudah diperbaiki pada "
        "blok json. Jangan melemahkan test atau menonaktifkan security check."
    ),
    "format_repair": (
        "Jawabanmu sebelumnya tidak bisa diparse karena format JSON-nya bermasalah. "
        "Kirim ulang HANYA blok ```json yang valid sesuai skema, tanpa mengubah isi "
        "usulanmu."
    ),
}


def render_prompt(template: str, *, idea: str = "", context: str = "",
                  role: str = "", round_no: int = 1, disputes: str = "",
                  findings: str = "") -> str:
    """Render template prompt + footer instruksi blok JSON.

    ``ValueError`` bila nama template tidak dikenal. Placeholder yang
    tidak diisi dibiarkan kosong (bukan error) agar template bisa dipakai
    sebagian.
    """
    if template not in PROMPT_TEMPLATES:
        raise ValueError(f"Template prompt tidak dikenal: {template!r}")
    body = PROMPT_TEMPLATES[template].format(
        idea=idea, context=context, role=role, round_no=round_no,
        disputes=disputes, findings=findings,
    )
    if template == "format_repair":
        return body
    return body + JSON_FOOTER
