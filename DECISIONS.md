# DECISIONS.md — Keputusan MUFAKAT

Dokumen ini memisahkan dua hal: **(A)** keputusan yang sudah diambil
(arsitektur) dan **(B)** keputusan terbuka yang butuh persetujuan owner.
Hal yang belum terverifikasi ditulis apa adanya sebagai
**belum terverifikasi** — jangan dianggap sudah diputuskan.

## A. Keputusan arsitektur yang sudah diambil

| # | Keputusan | Alasan / catatan |
|---|-----------|------------------|
| A1 | **LangGraph satu-satunya orkestrator** | Satu graph untuk alur debat → rapat → kode → audit → test → ulang. Tidak ada orkestrator kedua (mis. CrewAI/LangChain agent framework lain) agar state dan retry terpusat. Bila modul graph belum ada, CLI/MCP/Web memakai fallback penulisan langsung dan tidak gagal total. |
| A2 | **Satu server MCP** | Satu server FastMCP bernama `mufakat`, transport stdio. Semua domain (core, meeting, task, project, git, filesystem, terminal, testing, security, research, evaluation, approval, observability) adalah tool di server yang sama, bukan server terpisah. |
| A3 | **SQLite default** | Penyimpanan terstruktur memakai SQLite (SQLModel) dengan tabel `runs`, `messages`, `gate_results`, `usage_ledger` (+ entitas kolaborasi). Path DB dari `MUFAKAT_DB`; bila tidak ada, pembacaan mengembalikan list kosong. Transkrip utama tetap JSONL di `runs/<run_id>/transcript.jsonl`. |
| A4 | **Protokol pesan MufakatMessage** | Satu pesan per baris JSONL, sesuai JSON Schema §8 dokumen arsitektur (field wajib: `run_id`, `round`, `phase`, `agent_id`, `role`, `model_family`, `content`, `timestamp`). Ringkasan maks. 1.200 karakter per agen per ronde. |
| A5 | **Konsensus: Borda count + voting** | Moderator menghitung Borda count dari ranking dan vote `approve/revise/reject`. Mufakat = usulan teratas didukung ≥ 2/3 agen dengan `approve` dan tanpa kritik `blocking` yang belum dijawab. Setelah ronde 3 tanpa mufakat, juri memutus dan dissent dicatat di spesifikasi. |
| A6 | **Anonimitas saat peer-review** | Jawaban ronde 1 dibuat tanpa melihat jawaban lain; kritik memakai label anonim (A/B/C, urutan diacak). |
| A7 | **Keamanan: tanpa otomasi web chat** | Hanya CLI/API resmi provider. Dilarang membaca kredensial CLI provider lain. `terminal_run` (MCP) hanya mengizinkan `echo`/`ls`/`pytest` tanpa shell. |
| A8 | **Gate sebelum merge** | Kode hanya masuk repo setelah gate keamanan & pengujian lolos; hasilnya disimpan di `runs/<run_id>/gates/` (JSON/SARIF). Tanpa hasil gate, `gate_report` mengembalikan status `belum terverifikasi`. |
| A9 | **CLI sebagai antarmuka utama** | Entry point `mufakat` (Typer): `run`, `debate`, `resume`, `status`, `doctor`. Web dan MCP memakai logika run yang sama (`mufakat.runner`). |

## B. Keputusan terbuka — butuh persetujuan owner

| # | Keputusan | Status | Opsi / catatan |
|---|-----------|--------|----------------|
| B1 | **Provider debat default** | **Belum terverifikasi** — belum ada keputusan owner | Kandidat rantai debater: `deepseek → openrouter_free → groq → gemini_api` (lihat `config/providers.yaml`). Perlu dipilih mana yang jadi default dan berapa batas biaya per run (`MUFAKAT_MAX_COST_USD`, saat ini contoh 1.0). |
| B2 | **Langganan Claude Pro vs ChatGPT Plus** | **Belum terverifikasi** — belum ada keputusan owner | Apakah owner berlangganan salah satu / keduanya / tidak sama sekali? Berpengaruh ke adapter CLI yang dipakai (Codex, Claude, Copilot) dan kuota. Tanpa langganan, jalur `mock`/API gratis yang dipakai. |
| B3 | **Hosted MT5 (MetaTrader 5)** | **Belum terverifikasi** — belum ada keputusan owner | Apakah trading MT5 di-host (VPS/server) atau lokal saja? Berpengaruh ke konektor MT5 dan keamanan kredensial broker. |
| B4 | **Integrasi Figma** | **Belum terverifikasi** — belum ada keputusan owner | Apakah Figma dihubungkan via MCP (Figma MCP server) dan dengan token siapa? Perlu persetujuan sebelum token apa pun disimpan. |
| B5 | **Integrasi Canva** | **Belum terverifikasi** — belum ada keputusan owner | Sama seperti Figma: via MCP atau tidak sama sekali. |
| B6 | **MCP ke aplikasi OpenBot / Antigravity** | **Belum terverifikasi** — masih proposal kondisional | Opsi yang pernah disebut: Muse membangun MCP, atau owner memberi Muse MCP-nya sendiri agar bisa bekerja langsung di aplikasi. Belum ada keputusan atau MCP yang dibangun. |
| B7 | **Provider coding default** | **Belum terverifikasi** — belum ada keputusan owner | Kandidat rantai coder: `codex → opencode_free → qwen_api`. |
| B8 | **Batas biaya & kuota harian** | **Belum terverifikasi** — belum ada keputusan owner | Token bucket per provider dan batas biaya per run/hari di `config/providers.yaml` masih nilai contoh dan perlu disetujui owner. |
| B9 | **Penyimpanan run jangka panjang** | **Belum terverifikasi** — belum ada keputusan owner | Saat ini run tersimpan lokal di `runs/` + SQLite lokal. Apakah perlu backup/cloud atau retensi tertentu? |

## C. Cara mengubah dokumen ini

- Keputusan baru yang sudah disetujui owner: pindahkan dari bagian B ke
  bagian A dengan tanggal dan sumber keputusan.
- Jangan mengubah status **belum terverifikasi** menjadi diputuskan tanpa
  konfirmasi eksplisit dari owner.

## Keputusan integrasi (diambil saat pembangunan, 20 Nov 2026)

- **Layout kanonik: `src/mufakat/`** (sesuai Claude §7 dan `pyproject.toml` src-layout). Tree flat di root repo (`adapters/`, `consensus/`, `graph/`, `gates/`, `router/`, `sandbox/` di root) yang dibuat paralel oleh subagent sudah dipindah ke `src/mufakat/` dan dihapus dari root, karena tree flat membuat root menjadi paket `mufakat` bayangan dan memecah `isinstance` GateResult saat paket terimpor dua kali. `tests/test_smoke.py` yang menghapus `sys.modules` saat import juga sudah diperbaiki.
- **Checkpointer LangGraph:** `langgraph-checkpoint-sqlite` ditambahkan ke dependensi; bila paket itu tidak ada, graph jatuh ke `MemorySaver` (bukan gagal total).
- **Node graph async:** runner memakai `ainvoke` (invoke sinkron LangGraph menolak node async).
