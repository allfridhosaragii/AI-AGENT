# MUFAKAT — Musyawarah untuk Mufakat

Sistem multi-AI agent: satu ide masuk, beberapa AI berdebat, saling mengkritik
dan mengoreksi, lalu menghasilkan spesifikasi, kode, audit, dan test — diulang
sampai aman dan mencapai mufakat.

> **Status (20 Nov 2026):** prototipe. Jalur `mock` sudah jalan end-to-end
> (CLI → run → worktree + diff + gates nyata → transkrip → spec → laporan,
> MCP 15 domain, A2A format, dashboard web). **Test: 71 passed, 1 skipped,
> 0 failed; ruff bersih; mypy bersih** (lihat [SELF_AUDIT.md](SELF_AUDIT.md)).
> Debat multi-provider asli menunggu API key / login CLI owner di
> [DECISIONS.md](DECISIONS.md).

## Instalasi

Butuh Python 3.12+. **Tidak perlu `uv`** — bila `uv` tidak ada, pakai `pip` biasa.

```bash
git clone <repo-mufakat>
cd mufakat
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                 # instalasi editable + entry point `mufakat`
pip install -e ".[dev]"          # + pytest, ruff, mypy
```

Periksa instalasi:

```bash
mufakat --help
mufakat doctor
```

## Isi `.env`

Salin contoh, lalu isi hanya key yang memang dipakai. **Jangan pernah commit
file `.env` yang sudah terisi.**

```bash
cp .env.example .env
```

Isi `.env.example` (contoh):

```dotenv
DEEPSEEK_API_KEY=<redacted>
OPENROUTER_API_KEY=<redacted>
GEMINI_API_KEY=<redacted>
GROQ_API_KEY=<redacted>
META_API_KEY=<redacted>
MUFAKAT_DB=
MUFAKAT_MAX_COST_USD=1.0
```

`mufakat doctor` hanya memeriksa **ada/tidak**-nya key — nilainya tidak pernah
ditampilkan di layar maupun log.

## Contoh pemakaian CLI

```bash
# Pipeline penuh (mock bila provider belum terhubung)
mufakat run "Buat REST API todo dengan FastAPI + test + audit"

# Debat saja — hasilnya spec.md
mufakat debate "Buat REST API todo dengan FastAPI + test + audit"

# Lihat status & lanjutkan run
mufakat status <run_id>
mufakat resume <run_id>

# Periksa binary, API key (ada/tidak), dan Docker
mufakat doctor
```

Setiap run menulis ke `runs/<run_id>/`:

- `transcript.jsonl` — satu `MufakatMessage` per baris
- `rounds/round-01.md` — ringkasan ronde (tabel vote, kritik)
- `spec.md`, `final_report.md`, `status.json`
- `worktree/` — kode nyata hasil node code (`main.py`, `test_main.py`)
- `diff/iter-01.patch` — unified diff worktree
- `gates/` — `semgrep.json`, `bandit.json`, `gitleaks.json`,
  `trivy.json`, `pytest.json`, `lint.json`, `verdict.json` (AMAN/TIDAK AMAN)

Contoh hasil nyata (mock, 20 Nov 2026): `mufakat run "Buat REST API todo
dengan FastAPI + test + audit"` selesai ±12 detik, verdict **AMAN**.

## Dashboard web

```bash
uvicorn mufakat.web.app:app --reload
# buka http://127.0.0.1:8000
```

Endpoint: `GET /`, `/health`, `/api/projects`, `/api/runs`,
`/api/runs/{run_id}`, `/api/meetings`, `/api/tasks`, `/api/approvals`,
`/api/usage`, `/api/audit`, dan `POST /api/debate` (`{"topic": "..."}`).
Data dibaca dari folder `runs/` dan SQLite bila ada; bila tidak ada,
endpoint mengembalikan list kosong + status `ok`.

## Server MCP

Satu server FastMCP bernama `mufakat`, transport stdio:

```bash
mufakat-mcp
```

Uji dengan MCP Inspector:

```bash
npx @modelcontextprotocol/inspector mufakat-mcp
# atau, bila entry point belum terpasang:
npx @modelcontextprotocol/inspector python -m mufakat.mcp_server.server
```

Tool yang tersedia: `debate_start`, `debate_status`, `pipeline_run`,
`gate_report`, `core_list_agents`, `meeting_create`, `task_create`,
`project_create`, `git_status`, `filesystem_read`, `terminal_run`,
`testing_run`, `security_scan`, `research_search`, `evaluation_submit`,
`approval_request`, `observability_status` — total **55 tool dari
15 modul domain** di `src/mufakat/mcp_server/domains/` (core,
communication, meeting, task, memory, project, git, filesystem,
terminal, testing, security, research, evaluation, approval,
observability), masing-masing dengan kontrak + permission
(`read` / `propose` / `write-sandbox` / `execute-approved` /
`approval-required`). `git_commit` hanya jalan dengan approval yang
disetujui; tidak pernah push.

## Postgres/Redis (opsional)

```bash
pip install -e ".[postgres]"   # psycopg
pip install -e ".[redis]"      # redis
docker compose up -d           # Postgres 16 + Redis 7 (lihat docker-compose.yml)
DATABASE_URL=postgresql://mufakat:mufakat@localhost:5432/mufakat mufakat run "..."
REDIS_URL=redis://localhost:6379/0 mufakat run "..."
```

Tanpa `DATABASE_URL`/`REDIS_URL`, MUFAKAT memakai SQLite dan cache
in-memory — Postgres/Redis tidak wajib.

## A2A (format saja)

Modul `src/mufakat/a2a/` mengimplementasikan format protokol A2A
(Agent Card JSON, Task/Message/Artifact, dispatcher lokal). Interop
dengan agent A2A eksternal **belum terverifikasi** dan tidak diklaim.

## Batasan & ToS — penting

- **Jangan mengotomasi web chat** (ChatGPT web, Claude web, dsb.): MUFAKAT
  hanya memakai CLI resmi / API resmi provider, sesuai ketentuan layanan
  masing-masing. Modul `security.check_no_webchat_automation` menolak
  perintah yang mengarah ke otomasi web chat.
- **Jangan membaca kredensial CLI** (file konfigurasi/token CLI provider
  lain). API key hanya dibaca dari environment / `.env` milik pengguna.
- **Jangan menjalankan perintah berbahaya lewat MCP**: `terminal_run`
  hanya mengizinkan `echo`, `ls`, dan `pytest` (tanpa shell, tanpa
  metakarakter). `filesystem_read` menolak file rahasia (`.env`,
  `*secret*`, `*.pem`, `*.key`, dsb.).
- **Biaya & kuota**: debat memakai ringkasan ronde sebelumnya (maks.
  1.200 karakter per agen), bukan transkrip penuh; ada token bucket per
  provider dan circuit breaker setelah 3 error 429/5xx berturut-turut
  (lihat `config/providers.yaml`).

## MUFAKAT Room — rapat multi-AI via login browser (manual handoff default)

> **Disclaimer ToS (Claude §0.4):** "Mengotomasi web chat bisa melanggar
> Ketentuan Layanan penyedia AI. MUFAKAT Room dirancang semi-manual (Anda yang
> menekan Kirim) untuk meminimalkan risiko, tetapi risiko pembatasan akun tetap
> ada dan menjadi tanggung jawab pengguna. Gunakan akun sendiri, untuk proyek
> sendiri, dengan kecepatan wajar."

**Konflik yang diselesaikan dengan jujur (Claude ROOM vs ChatGPT V3):**
dokumen Claude memakai Chrome Extension (fillInput + readLastReply DOM)
sebagai moderator, sedangkan V3 **melarang** extension dan DOM
scraping/automasi pada MVP dan mewajibkan Manual Handoff sebagai default.
Gabungan yang dipakai: **mode default adalah MANUAL HANDOFF** (V3 §2.2 Mode B)
— pengguna menyalin prompt, mengirim sendiri di tab resmi provider, lalu
menempel jawaban kembali (dilabeli "user imported" + provenance). Assisted
Fill via extension HANYA modul opt-in Fase 2, terpisah, tidak aktif secara
default. Jangan pernah klaim koneksi otomatis bila hanya manual handoff.

**Status per provider (jujur):** ChatGPT, Claude, Gemini, DeepSeek, Qwen =
`manual_handoff` ("Manual handoff only"); Muse = `needs_policy_review`
(identitas situs/kebijakan belum terverifikasi). Lihat
`src/mufakat/room/providers.py`.

**Engine Python** (`src/mufakat/room/`): `handoff.py` (state machine V3
Addendum F: DRAFT → READY_TO_SEND → WAITING_FOR_USER_SUBMISSION →
WAITING_FOR_IMPORTED_RESPONSE → RESPONSE_IMPORTED → CRITIQUE_READY →
WAITING_FOR_REBUTTAL_IMPORT → REVISION_READY → FINAL_REVIEW → APPROVED),
`secret_scan.py`, `pacing.py` (jeda 20 dtk/situs, batas harian default 40),
`parser.py` (blok ```json terakhir, ok/repair_needed/unparsed, maks 1x
repair), `providers.py`, `prompts.py`, `state_machine.py` (Claude §2),
`anti_loop.py`, `storage.py` (SQLite + JSONL; padanan Dexie di browser).
Konsensus Borda reuse `mufakat.consensus.voting` — tidak ada logika ganda.

**Extension scaffold** (`mufakat-room/`, WXT/React/TS): manifest MV3 permission
minimal (`sidePanel`, `storage`, `unlimitedStorage`, `clipboardWrite`,
`nativeMessaging` + 6 host permission saja), 6 content script adapter
(`fillInput` HANYA isi teks, TIDAK kirim), `selectors.json` versioned
(`lastVerified: "belum terverifikasi"`), Selector Doctor, engine TS
(stateMachine, parser, consensus, pacing, antiLoop, secretScan), storage
Dexie, `runnerClient.ts`. **Belum terverifikasi:** `pnpm` tidak tersedia di
VM ini, jadi `pnpm install`/`pnpm dev`/vitest belum pernah jalan.

**Local Runner** (`mufakat-room/runner/`, Python stdlib): native messaging
host length-prefixed (`init_workspace`, `apply_files`, `run_gates`, `diff`,
`commit` — hanya dengan approval token sekali pakai — `cleanup`, `status`),
`worktree.py` (tolak path traversal), `sandbox.py` (Docker non-root,
`--network none`), `gates/` + `verdict.py` (reuse `mufakat.gates`), `mcp_server.py`
(tool `room_status`, `gate_report`, `run_gates`). **Docker belum
terverifikasi** di VM ini (binary `docker` tidak ada); sandbox mengembalikan
`verified: false`, bukan pura-pura jalan.

**Demo mock end-to-end** (tanpa situs AI asli):

```bash
.venv/bin/python -m mufakat.room.demo "Buat REST API todo dengan FastAPI + test + audit"
# menulis runs/room-mock-<id>/final_report.md
```

**Yang masih manual (dilakukan pengguna di website AI):** login di tiap situs,
menekan Kirim, menyalin/menempel jawaban, menyetujui patch & commit. Lihat
[BLUEPRINT.md](BLUEPRINT.md) §17 dan [DECISIONS.md](DECISIONS.md) A16–A18, B10.

## Cara menambah provider baru

1. Buat adapter di `src/mufakat/adapters/` mengikuti `adapters/base.py`
   (contoh: `adapters/cli_codex.py`, `adapters/api_openai_compat.py`).
2. Daftarkan provider + kapabilitasnya di `src/mufakat/provider_registry.py`.
3. Tambahkan fallback-nya di `config/providers.yaml` (rantai per peran,
   mis. debater: `deepseek → openrouter_free → groq → gemini_api`).
4. Tambahkan API key-nya ke `.env.example` dan `.env` (jangan commit `.env`).
5. Tambahkan tes di `tests/` dan jalankan `pytest`.
6. Bila provider memakai CLI, pastikan `mufakat doctor` mendeteksinya
   (tambah ke daftar binary di `src/mufakat/cli.py` bila perlu).

## Pengujian & lint

```bash
pytest
ruff check src tests
mypy src
```

Hasil 20 Nov 2026: **71 passed, 1 skipped, 0 failed** (pytest),
ruff bersih, mypy bersih (81 file). 1 skip = catatan Playwright
belum terpasang (E2E dashboard memakai TestClient — lihat
`tests/e2e/`).

## Yang masih butuh owner (real testing)

- **Debat multi-AI sungguhan:** isi salah satu API key
  (`DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`,
  `GROQ_API_KEY`, `META_API_KEY`) atau login CLI (`codex login`,
  `copilot`, `claude`, `agy`, `opencode`). Adapter CLI hanya dipakai
  bila login terverifikasi (`is_available()`); tanpa itu, mock.
- **Binary gate:** `gitleaks`/`trivy` tidak ada di VM; `semgrep`
  tidak bisa satu venv dengan FastMCP (konflik `mcp` 1.29 vs 2.3) —
  gate memakai fallback regex / INFO "belum terverifikasi".
- **Docker:** binary `docker` tidak ada di VM — sandbox Docker belum
  terverifikasi.
- **Playwright:** belum terpasang — E2E browser belum ada.
- **Figma/Canva/MT5, OpenBot/Antigravity, multi-user, deployment:**
  belum dibangun / butuh keputusan owner.

Sengaja tidak dibangun (deferred): desktop Tauri, Temporal, sandbox
cloud E2B/Daytona — lihat DECISIONS.md A15.

## Struktur

```text
src/mufakat/
  cli.py            # Typer: run, debate, resume, status, doctor
  runner.py         # Logika run bersama (CLI, MCP, Web)
  mcp_server/       # Satu server FastMCP + tools aman
  web/              # FastAPI + dashboard statis (tanpa build Node)
  consensus/        # Protokol MufakatMessage
  storage/          # Transkrip JSONL + SQLite (SQLModel)
  adapters/         # Adapter provider (CLI/API)
  router/           # Kuota, budget, fallback
  graph/            # LangGraph (satu-satunya orkestrator)
config/             # providers.yaml, roles.yaml, gates.yaml, prompts/
runs/               # Output run (tidak di-commit bila berisi data nyata)
```

## Keputusan yang masih terbuka

Lihat [DECISIONS.md](DECISIONS.md) — antara lain provider debat default,
langganan Claude Pro vs ChatGPT Plus, dan hosted MT5/Figma. Semuanya
ditandai **belum terverifikasi** bila belum ada sumber/keputusan owner.
