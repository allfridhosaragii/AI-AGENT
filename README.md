# MUFAKAT — Musyawarah untuk Mufakat

Sistem multi-AI agent: satu ide masuk, beberapa AI berdebat, saling mengkritik
dan mengoreksi, lalu menghasilkan spesifikasi, kode, audit, dan test — diulang
sampai aman dan mencapai mufakat.

> **Status (20 Nov 2026):** prototipe. **Produk utama (MVP) adalah
> Browser-Only AI Room** — lihat [Produk utama (MVP)](#produk-utama-mvp-browser-only-ai-room)
> di bawah. Jalur `mock` sudah jalan end-to-end (CLI → run → worktree +
> diff + gates nyata → transkrip → spec → laporan, MCP 15 domain, A2A
> format, dashboard web).
>
> **Angka test yang jujur (dijalankan 20 Nov 2026, 21:00 WIB, Python
> 3.12.3, pytest 9.2.0):** setelah perbaikan audit putaran 2 — inti
> **242 passed, 1 skipped, 0 failed**; Local Runner
> **62 passed, 0 failed**; `ruff check` bersih; `mypy
> --check-untyped-defs` bersih (0 error, 96 file); `bandit` 0 High,
> 0 Medium. Audit eksternal putaran 2 (sebelum perbaikan)
> mendapat **3 failed, 171 passed, 1 skipped** di mesin dengan CLI Docker tanpa daemon. Docker TIDAK tersedia
> di VM ini, jadi gate nyata mengembalikan **BELUM_TERVERIFIKASI**
> (fail-closed, bukan AMAN) sampai Docker terpasang — lihat
> [SELF_AUDIT.md](SELF_AUDIT.md).
> Debat multi-provider asli menunggu API key / login CLI owner di
> [DECISIONS.md](DECISIONS.md).
>
> **Lisensi:** MIT (lihat [LICENSE](LICENSE)) — keputusan sementara
> yang bisa diubah owner.

## Produk utama (MVP): Browser-Only AI Room

Satu-satunya produk utama MUFAKAT adalah **Browser-Only AI Room**:
pengguna login di website resmi AI (ChatGPT, Claude, Gemini, DeepSeek,
Qwen) di browsernya sendiri, menyalin prompt dari Room, mengirim sendiri,
lalu menempel jawaban kembali (manual handoff). Tidak ada otomasi web
chat, tidak ada pembacaan cookie/token, tidak ada auto-send.

Komponen MVP:

- **Room Dashboard** — daftar rapat, fase, timeline, dan laporan.
- **Prompt Manager** — susun prompt per peran/fase (ronde 1, kritik,
  rapat, voting, spesifikasi).
- **Room Engine** — state machine rapat (DRAFT → … → APPROVED),
  anti-loop, dan pacing (jeda 20 dtk/situs, batas harian 40).
- **Answer Import** — impor jawaban dengan provenance ("user imported",
  provider, ronde, waktu impor) dan secret scan SEBELUM disimpan.
- **Consensus Engine** — Borda count + voting 2/3, satu-satunya mesin
  konsensus Room.
- **IndexedDB** (Dexie di browser; padanan SQLite/JSONL di layanan
  Python) — state rapat persisten, tidak hilang saat reload.
- **Website resmi AI** — tempat satu-satunya interaksi dengan provider.

**Satu-satunya engine AI Room di web adalah engine TypeScript** di
website Room (artifact `mufakat`). Engine Python di `src/mufakat/room/`
adalah layanan backend terpisah / referensi yang sinkron dengan engine
TS — bukan engine kedua yang berjalan sendiri-sendiri. Sumber kebenaran
tunggal per lapisan: UI/state web = engine TS; logika handoff, pacing,
secret scan, dan konsensus Python = `src/mufakat/room/` (dipakai CLI,
MCP, dan demo mock); keduanya harus dijaga sinkron, dan bila berbeda,
yang berlaku adalah perilaku yang terdokumentasi di
[BLUEPRINT.md](BLUEPRINT.md) §17–§18.

## Modul Opsional / Legacy — bukan MVP

Jalur di bawah ini **TIDAK dihapus dari repo**, tetapi **bukan MVP**:
tidak aktif secara default, tidak dipakai Room, dan butuh keputusan
owner sebelum dipakai atau diaktifkan kembali (lihat
[DECISIONS.md](DECISIONS.md) A9, A16, B10).

- **Adapter CLI AI** (`src/mufakat/adapters/`) — menjalankan CLI
  provider (codex, claude, copilot, dsb.); hanya dipakai bila login
  terverifikasi, dan hanya di jalur legacy.
- **API key provider** — debat via API resmi; menunggu keputusan dan
  key owner (B1, B2, B7, B8).
- **Content scripts / DOM scraping** (`mufakat-room/src/adapters/`,
  `src/entrypoints/*.content.ts`) — `fillInput`/`readLastReply`;
  bagian dari extension, bukan MVP.
- **Assisted Fill** — pengisian otomatis via extension; opt-in Fase 2,
  TIDAK AKTIF, tidak ada di UI utama MVP.
- **Native Messaging / Local Runner** (`mufakat-room/runner/`) —
  eksekusi kode lokal via host native; modul terpisah, bukan jalur Room.
- **Server MCP 15 domain, LangGraph pipeline CLI, dashboard FastAPI**
  (`src/mufakat/`) — layanan backend/referensi; tetap ada dan teruji,
  tetapi bukan produk utama.

Bagian "Contoh pemakaian CLI", "Server MCP", dan "Cara menambah provider
baru" di bawah mendokumentasikan jalur opsional/legacy ini.

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

**Lockfile dependensi:** `requirements.lock` (141 paket ter-pin,
dihasilkan 20 Nov 2026 dari `.venv` via `pip freeze`; `uv` tidak
tersedia di VM jadi `uv.lock` belum ada) dan pin versi di
`pyproject.toml`. Lockfile extension (`package-lock.json` /
`pnpm-lock.yaml`) **belum ada** — `npm install` gagal karena
`@types/turndown@^4.0.0` tidak ada (versi terbaru 5.0.6); perbaikan
menjadi `^5.0.5` dan pembuatan lockfile adalah tugas worker ekstensi
(lihat [SELF_AUDIT.md](SELF_AUDIT.md)).

**CI:** `.github/workflows/ci.yml` (ruff, mypy, pytest inti + runner,
typecheck + vitest + `wxt build` extension, gitleaks). File ini tidak
bisa di-push via GitHub API (GitHub App diblokir untuk file workflow)
— tambahkan manual lewat web GitHub, lihat komentar di kepala file CI.

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

## Contoh pemakaian CLI (jalur opsional/legacy — bukan MVP)

> Jalur CLI di bawah ini adalah modul opsional/legacy, bukan produk
> utama. Produk utama adalah Browser-Only AI Room di atas.

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
  `trivy.json`, `pytest.json`, `lint.json`, `verdict.json`
  (AMAN / TIDAK AMAN / BELUM_TERVERIFIKASI — tanpa Docker, gate
  gagal-tertutup menjadi BELUM_TERVERIFIKASI, bukan AMAN)

Contoh hasil nyata (mock, 20 Nov 2026): `mufakat run "Buat REST API todo
dengan FastAPI + test + audit"` selesai ±12 detik; tanpa Docker di VM
ini verdict-nya **BELUM_TERVERIFIKASI** (semua gate butuh sandbox).

## Dashboard web (layanan backend/referensi — bukan produk utama)

```bash
uvicorn mufakat.web.app:app --reload
# buka http://127.0.0.1:8000
```

Endpoint: `GET /`, `/health`, `/api/projects`, `/api/runs`,
`/api/runs/{run_id}`, `/api/meetings`, `/api/tasks`, `/api/approvals`,
`/api/usage`, `/api/audit`, dan `POST /api/debate` (`{"topic": "..."}`).
Data dibaca dari folder `runs/` dan SQLite bila ada; bila tidak ada,
endpoint mengembalikan list kosong + status `ok`.

> **Local-only secara default:** tanpa autentikasi, dashboard ini
> HANYA untuk localhost pribadi — jangan expose ke publik. Bila
> dipakai publik, set env `MUFAKAT_WEB_TOKEN`; `POST /api/debate`
> lalu mewajibkan header `X-MUFAKAT-TOKEN`.

## Server MCP (jalur opsional/legacy — bukan MVP)

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
`approval_request`, `observability_status` — total **54 tool dari
15 modul domain** di `src/mufakat/mcp_server/domains/` (core,
communication, meeting, task, memory, project, git, filesystem,
terminal, testing, security, research, evaluation, approval,
observability), masing-masing dengan kontrak + permission
(`read` / `propose` / `write-sandbox` / `execute-approved` /
`approval-required`). `git_commit` hanya jalan dengan approval
manusia yang disetujui lewat `mufakat approve` + token sekali pakai
yang terikat hash diff; tidak pernah push. Tool
`approval_record_decision` sudah DIHAPUS dari MCP (audit H1) — AI
tidak bisa menyetujui commit-nya sendiri.

## Postgres/Redis (opsional)

```bash
pip install -e ".[postgres]"   # psycopg
pip install -e ".[redis]"      # redis
cp .env.example .env           # isi POSTGRES_PASSWORD & REDIS_PASSWORD (wajib)
docker compose up -d           # Postgres 16 + Redis 7, hanya 127.0.0.1 (lihat docker-compose.yml)
DATABASE_URL=postgresql://mufakat:<POSTGRES_PASSWORD>@localhost:5432/mufakat \
REDIS_URL=redis://:<REDIS_PASSWORD>@localhost:6379/0 mufakat run "..."
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
  hanya mengizinkan `echo` dan `ls` (tanpa shell, tanpa metakarakter);
  `pytest` HANYA lewat gate sandbox Docker. `filesystem_read` hanya
  boleh di dalam allowlist folder workspace/repo (`runs/`), menolak
  symlink, folder kredensial (`~/.ssh`, `~/.codex`, `~/.config`,
  `~/.claude`, `~/.gemini`, `~/.aws`) dan `*.sqlite`.
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

**Engine Python** (`src/mufakat/room/`): layanan backend terpisah /
referensi yang sinkron dengan engine TypeScript di web — bukan engine
kedua yang berjalan sendiri-sendiri (lihat "Produk utama (MVP)" di atas
dan BLUEPRINT §18). `handoff.py` (state machine V3
Addendum F: DRAFT → READY_TO_SEND → WAITING_FOR_USER_SUBMISSION →
WAITING_FOR_IMPORTED_RESPONSE → RESPONSE_IMPORTED → CRITIQUE_READY →
WAITING_FOR_REBUTTAL_IMPORT → REVISION_READY → FINAL_REVIEW → APPROVED),
`secret_scan.py`, `pacing.py` (jeda 20 dtk/situs, batas harian default 40),
`parser.py` (blok ```json terakhir, ok/repair_needed/unparsed, maks 1x
repair), `providers.py`, `prompts.py`, `state_machine.py` (Claude §2),
`anti_loop.py`, `storage.py` (SQLite + JSONL; padanan Dexie di browser).
Konsensus Borda reuse `mufakat.consensus.voting` — tidak ada logika ganda.

**Extension scaffold** (`mufakat-room/`, WXT/React/TS — modul opsional
Fase 2, BUKAN MVP, tidak aktif default): manifest MV3 permission
minimal (`sidePanel`, `storage`, `unlimitedStorage`, `clipboardWrite`,
`nativeMessaging` + 6 host permission saja), 6 content script adapter
(`fillInput` HANYA isi teks, TIDAK kirim), `selectors.json` versioned
(`lastVerified: "belum terverifikasi"`), Selector Doctor, engine TS
(stateMachine, parser, consensus, pacing, antiLoop, secretScan), storage
Dexie, `runnerClient.ts`. **Belum terverifikasi:** `pnpm` tidak tersedia di
VM ini, jadi `pnpm install`/`pnpm dev`/vitest belum pernah jalan.

**Local Runner** (`mufakat-room/runner/`, Python stdlib — modul
opsional/legacy, BUKAN MVP, tidak dipakai Room): native messaging
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

## Cara menambah provider baru (jalur opsional/legacy — bukan MVP)

1. Buat adapter di `src/mufakat/adapters/` mengikuti `adapters/base.py`
   (contoh: `adapters/cli_codex.py`, `adapters/api_openai_compat.py`).
2. Daftarkan provider + kapabilitasnya di `src/mufakat/provider_registry.py`.
3. Tambahkan fallback-nya di `config/providers.yaml` (rantai per peran,
   mis. debater: `deepseek → openrouter → groq → gemini`).
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

Hasil perbaikan audit putaran 2, 20 Nov 2026 (dijalankan 21:00 WIB,
Python 3.12.3, pytest 9.2.0): **inti 242 passed, 1 skipped,
0 failed**; **Local Runner 62 passed, 0 failed**; `ruff check`
bersih; `mypy --check-untyped-defs` bersih (0 error, 96 file);
`bandit` 0 High, 0 Medium. Docker tidak tersedia di VM
ini sehingga gate nyata berstatus **BELUM_TERVERIFIKASI**. Lihat
[SELF_AUDIT.md](SELF_AUDIT.md) untuk rincian dan status perbaikan.
Angka "174 passed" dari audit putaran 1 sudah tidak berlaku.

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
