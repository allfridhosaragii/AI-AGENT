# SELF_AUDIT.md — Audit mandiri kode MUFAKAT sendiri

Tanggal: **20 Nov 2026**. Perintah: jalankan tool gate yang tersedia di
VM ini pada kode MUFAKAT sendiri, simpan hasilnya, perbaiki temuan yang
nyata dan aman diperbaiki. Yang tidak tersedia dicatat sebagai
**belum terverifikasi** — bukan "lolos".

## Audit eksternal 20 Nov 2026 (ChatGPT) — angka lama TIDAK BERLAKU

Tanggal: **20 Nov 2026**. Auditor eksternal menjalankan ulang dari nol
dan memberi verdict **Belum layak digunakan** (3 Kritis, 7 Tinggi,
12 Sedang, 7 Rendah — lihat
`~/workspace/user/files/AUDIT-AI-AGENT-2026-11-20.md`).

Hasil yang benar-benar dijalankan auditor (bukan klaim):

| Perintah auditor | Hasil |
|---|---|
| `pip install -e ".[dev]" && pytest -q` | **6 failed, 149 passed, 1 skipped** |
| `(cd mufakat-room/runner && pytest -q)` | 33 passed |
| `ruff check src tests mufakat-room/runner` | bersih |
| `mypy src` | bersih |
| `mypy --check-untyped-defs src` | **6 error** |
| `bandit -r src mufakat-room/runner -f json` | 0 High, 0 Medium, 64 Low |
| `detect-secrets scan --all-files .` | hanya fixture test/contoh |
| `cd mufakat-room && npm install` | **GAGAL: `@types/turndown@^4.0.0` tidak ada** |
| `npx wxt build` | **GAGAL: No entrypoints found**, lalu Default export tidak ditemukan |
| `npx vitest run` | 11 passed (hanya engine, tanpa UI/adapter) |

**Konsekuensi:** angka "71 passed, 1 skipped, 0 failed" pada tabel
"Ringkasan hasil" di bawah adalah hasil self-audit lama dan **tidak bisa
direproduksi** — angka itu sudah tidak dipakai sebagai klaim di README
maupun BLUEPRINT §16. Tabel lama dibiarkan apa adanya sebagai riwayat,
dengan catatan ini sebagai koreksi.

## Yang benar-benar dijalankan di run perbaikan ini (20 Nov 2026, WIB)

Worker website/dokumentasi (run ini) — BUKAN run test suite:

| Perintah | Hasil |
|---|---|
| `.venv/bin/pip freeze` (Python 3.12.3, pip 26.3) | 141 paket ter-pin → `requirements.lock` (152 baris incl. header); pin langsung di `pyproject.toml` |
| `npm view @types/turndown version` (npm 10.9.4, Node v24.22.1) | **5.0.6** — memastikan `@types/turndown@^4.0.0` memang tidak ada |
| Pemeriksaan file rujukan SELF_AUDIT.md | Semua file yang dirujuk ada di repo (`src/mufakat/runner.py`, `a2a/__init__.py`, `storage/cache.py`, `mcp_server/domains/security.py`, `core.py`, `tools.py`, `__main__.py`, `adapters/_cli.py`, `tests/test_cli_adapters.py`, `tests/test_anti_loop.py`) |
| Pemeriksaan `~/workspace/audits/mufakat-room-2026-11-20.md` | Rujukannya (`client/src/App.tsx`, `server/src/actions.ts`, `server/src/schema.ts`, `client/src/api.ts`, `client/src/reference.ts`, …) adalah file INTERNAL website artifact slug `mufakat`, bukan file repo — ditambah catatan ruang lingkup di kepala file itu. Rujukan `audits/latest/` juga milik builder artifact, bukan direktori repo. |
| Pemeriksaan `~/workspace/audits/mufakat-room-ts-mirror-2026-11-20.md` | Rujukannya (`mufakat-room/src/engine/…`, `src/storage/db.ts`, `tests/engine.test.ts`, …) ada di repo. Tidak ada yang perlu diperbaiki. |

**Belum dijalankan di run ini (jujur, jangan diklaim):**

- `pytest -q` (inti maupun runner) setelah perbaikan audit — **belum
  dijalankan di run ini**. Angka terakhir yang benar-benar dijalankan
  tetap angka auditor di atas (6 failed, 149 passed, 1 skipped).
- `ruff check`, `mypy`, `bandit` setelah perbaikan — **belum dijalankan
  di run ini**.
- `npm install` / `wxt build` / `vitest` extension setelah perbaikan —
  **belum dijalankan di run ini**; lockfile extension
  (`package-lock.json`/`pnpm-lock.yaml`) **belum ada** dan menjadi
  tugas worker ekstensi (perlu perbaikan `@types/turndown` → `^5.0.5`
  dulu — `npm install` saat ini masih gagal).
- `uv lock` — **tidak bisa dihasilkan**: `uv` tidak tersedia di VM ini.
  `requirements.lock` (pip freeze) adalah pengganti yang jujur.
- Verifikasi website artifact (impor → reload → pacing → vote
  malformed) — **belum dijalankan di run ini**: `artifact.edit` tidak
  tersedia di subagent ini. Permintaan edit verbatim lengkap disimpan di
  `website-artifact-edit-request.md` untuk agen yang punya akses edit.

Laporan worker Python dan worker ekstensi run ini **belum ada** saat
dokumen ini ditulis (tidak ada laporan baru di `~/workspace/audits/`
selain dua file audit 20 Nov 2026 di atas); angka dari laporan itu
belum bisa diambil — bagian ini wajib diperbarui saat laporan tersebut
tersedia.

## Perbaikan audit Python C1–M12 + ChatGPT D/F/H/I — 20 Nov 2026 (worker Python)

Dijalankan **20 Nov 2026, 20:01 WIB** (13:01 UTC). Python 3.12.3,
pytest 9.2.0, ruff 0.17.6, mypy 2.4.1, bandit 1.9.4. Perintah persis:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider   # inti
(cd mufakat-room/runner && .venv/bin/python -m pytest -q -p no:cacheprovider)
.venv/bin/python -m ruff check src tests mufakat-room/runner
.venv/bin/python -m mypy --check-untyped-defs src
.venv/bin/python -m bandit -r src mufakat-room/runner -f json
docker --version   # tidak ada
```

| Perintah | Hasil (benar-benar dijalankan) |
|---|---|
| `pytest -q` (inti) | **174 passed, 1 skipped, 0 failed** (15,65 detik; 1 skip = catatan Playwright, sama seperti sebelumnya) |
| `pytest -q` (Local Runner) | **41 passed, 0 failed** |
| `ruff check src tests mufakat-room/runner` | **bersih** (0 error) |
| `mypy --check-untyped-defs src` | **bersih** (0 error, 94 file; audit eksternal: 6 error) |
| `mypy src` | **bersih** |
| `bandit -r src mufakat-room/runner -f json` | **0 High, 0 Medium, 153 Low** (audit eksternal: 0 High, 0 Medium, 64 Low — Low naik karena file/test baru; 2 Medium B108 lama diberi justifikasi `# nosec`) |
| `docker --version` | **tidak ada (`docker: command not found`)** — gate nyata berstatus **BELUM_TERVERIFIKASI** (fail-closed), bukan AMAN |
| `semgrep` / `gitleaks` / `trivy` binary | **tidak ada di VM** — gate diuji lewat fake sandbox runner di `tests/test_gates.py` (lihat bawah); Dockerfile diperbarui tapi **belum bisa di-build** tanpa Docker |

Catatan: suite inti kini hanya ±15 detik (dulu 106 detik) karena gate
di `create_run` tidak lagi mengeksekusi pytest di host — tanpa Docker
gate langsung gagal-tertutup `sandbox-unavailable`.

### Yang diperbaiki (per nomor audit)

- **C1:** semua gate (pytest, ruff, bandit, semgrep, gitleaks, trivy) dan
  `terminal_run`/`testing_run` pytest WAJIB lewat `run_in_sandbox()`;
  tanpa Docker → `passed=False`, `rule="sandbox-unavailable"`, verdict
  `BELUM_TERVERIFIKASI`. `pytest` dihapus dari allowlist terminal.
  Test regresi: `conftest.py` jahat tidak membuat file di host.
- **H7:** sandbox `--user 10001:10001`, workdir absolut, `--name
  mufakat-<uuid>` + `docker kill` saat timeout, `--cap-drop ALL`,
  `--security-opt no-new-privileges`, `--pids-limit 256`, `--read-only
  --tmpfs /tmp`, mount read-only untuk gate baca-saja; blocklist string
  dihapus. Dockerfile: versi di-pin + checksum SHA-256, build gagal
  bila tool hilang (tanpa `|| echo dilewati`); trivy **v0.76.2**
  (rilis 5 Nov 2026), gitleaks v8.30.1, semgrep 1.186.0, Node v20.20.2,
  ruff 0.17.6, bandit 1.9.4, pytest 9.2.0, pytest-cov 7.1.0.
  Dockerfile disatukan: `mufakat-room/docker/sandbox.Dockerfile` kini
  symlink ke `docker/sandbox.Dockerfile`.
- **C2:** host runner berbasis `run_id` + registry
  `~/.mufakat/runner.json` (perintah `register_repo`); `cleanup` hanya
  di bawah `<repo>/runs/<run_id>/wt`. Test: path di luar `runs/`
  ditolak untuk `apply_files`, `cleanup`, `run_gates`, `diff`, `commit`.
- **C3:** `filesystem_read` allowlist folder (cwd/`runs/`/env
  `MUFAKAT_WORKSPACE_ROOTS`); symlink ditolak; `~/.ssh`, `~/.config`,
  `~/.codex`, `~/.claude`, `~/.gemini`, `~/.aws`, `~/.git-credentials`,
  `*.sqlite` diblokir. Test: `~/.codex/auth.json` & `~/.ssh/id_ed25519`
  ditolak.
- **H1+H6:** `approval_record_decision` DIHAPUS dari MCP (54 tool
  terdaftar, dulu 55); approval hanya manusia via
  `mufakat approve <id>` (konfirmasi y/N di TTY, tampilkan diff+hash),
  disimpan di SQLite `runs/approvals.db`, terikat hash `git diff HEAD`,
  token sekali pakai (hash SHA-256, 24 jam). `git_commit` memverifikasi
  token + hash diff. Wrapper native host `mufakat-runner-host`
  (`.bat` untuk Windows); `install_host.py` tidak lagi memakai
  `sys.executable` dan di Windows benar-benar menulis manifest +
  registry key. Aliran token runner: `issue_approval_token` (UI tampilkan
  diff+hash → Approve → token).
- **H3+H4:** gate fail-closed (tool hilang → `BELUM_TERVERIFIKASI`);
  tanpa test → gagal; coverage nyata via `pytest --cov` +
  `GateResult.coverage`; regex hanya info tambahan. Bandit hanya gagal
  untuk HIGH/CRITICAL (diukur di bandit 1.9.4: B602/B324 HIGH, B307/B506
  MEDIUM, B101 LOW); B101 dikecualikan di `test_*.py`. Test adapter
  hermetis (mock `shutil.which`).
- **M1:** `SHELL_META` berisi `"\n\r"` asli. **M10:** checkpointer
  `SqliteSaver(sqlite3.connect(path, check_same_thread=False))` untuk
  konteks sinkron, `AsyncSqliteSaver` bila ada loop berjalan (graph
  async); `interrupt()` untuk approve spek (`require_human_approval`);
  `revise` kembali ke `review`. **M11:** compose hanya `127.0.0.1`,
  password dari `.env`, `requirepass` Redis. **M12:** `validate_run_id`
  di `read_run`, `gate_report_for_run`, `test_get_results`, dan web
  `GET /api/runs/{run_id}`.
- **ChatGPT I:** `openrouter_free`→`openrouter`, `gemini_api`→`gemini`
  di `config/providers.yaml`, `config/roles.yaml`, `runner.py`,
  `provider_registry.py`; `meta_api` berstatus `needs_policy_review`
  (llama-4-maverick TIDAK diklaim sebagai Muse Spark 1.3).
  **ChatGPT tabel:** web local-only secara default; bila
  `MUFAKAT_WEB_TOKEN` diset, `POST /api/debate` wajib header
  `X-MUFAKAT-TOKEN` (401 bila salah/tidak ada).
- **Test baru:** `tests/test_gates.py` (ditulis ulang + fake sandbox
  runner), `tests/test_audit_c1_c3.py`, `tests/test_audit_h1_m10.py`,
  `mufakat-room/runner/tests/test_runner.py` (+9 test C2/H6),
  `tests/test_room_runner.py` (run_id).

### Yang masih tersisa (jujur)

- **Docker tidak ada di VM ini** — image sandbox belum pernah di-build
  dan gate nyata belum pernah berjalan di container sungguhan. Semua
  gate diuji lewat fake sandbox runner (pytest/bandit/ruff sungguhan di
  host HANYA oleh test; semgrep/gitleaks/trivy diemulasikan dari pola
  regex). Perlu: mesin dengan Docker → `docker build -f
  docker/sandbox.Dockerfile .` lalu `pytest -q` (harapkan verdict AMAN
  untuk repo bersih, bukan BELUM_TERVERIFIKASI).
- **`semgrep`/`gitleaks`/`trivy` tidak terpasang di host** — gate
  mereka di luar sandbox tidak bisa diverifikasi langsung di VM ini.
- **H2, H5, M2–M9 dan Rendah (ekstensi TS + Room)** — di luar lingkup
  worker Python ini (ditangani worker ekstensi/website).
- **`store.approvals` (dict memori)** masih ada di
  `mcp_server/domains/store.py` sebagai sisa kompatibilitas, tetapi
  tidak lagi dipakai pengambilan keputusan commit.

## Ringkasan hasil

| Tool | Hasil | Keterangan |
|---|---|---|
| `pytest -q` | **71 passed, 1 skipped, 0 failed** (86 detik) — **TIDAK BERLAKU, lihat koreksi di atas** (audit eksternal: 6 failed, 149 passed, 1 skipped) | 1 skip = catatan Playwright belum terpasang |
| `ruff check src tests` | **Bersih** (0 error) | 7 error import-sorting diperbaiki (`ruff check --fix`) + 1 `import re` |
| `mypy src/mufakat --ignore-missing-imports` | **Bersih** (81 file, 0 error) | 3 error diperbaiki (cache typing, security annotation, `list_providers` tidak ada) |
| `bandit -r src` | **0 High, 0 Medium, 56 Low** | 1 Medium (B608 SQL injection) diperbaiki — lihat bawah |
| `semgrep` binary | **Belum terverifikasi** | Binary tidak ada; konflik `mcp` 1.29 vs 2.3 (lihat bawah). Gate semgrep memakai fallback regex deterministik |
| `gitleaks` binary | **Belum terverifikasi** | Binary tidak ada di VM; gate memakai fallback regex |
| `trivy` binary | **Belum terverifikasi** | Binary tidak ada di VM; gate mengembalikan INFO "trivy tidak tersedia" |
| `docker` | **Belum terverifikasi** | Binary tidak ada di VM; sandbox Docker belum bisa diuji |
| Playwright | **Belum terpasang** | E2E dashboard memakai TestClient (`tests/e2e/`) |

## Temuan yang diperbaiki

1. **Bandit B608 (Medium) — `src/mufakat/runner.py:548`.**
   Interpolasi nama tabel ke SQL (`SELECT * FROM "{table}"`).
   Perbaikan: validasi identifier ketat (`^[A-Za-z_][A-Za-z0-9_]*$`)
   + pengecekan keberadaan tabel di `sqlite_master` sebelum query,
   dan `# nosec B608` dengan alasan. Setelah perbaikan: 0 Medium.
2. **Ruff I001 (7x)** — import tidak terurut (termasuk
   `src/mufakat/a2a/__init__.py`). Diperbaiki dengan `ruff check --fix`.
3. **Mypy (3 error).**
   - `storage/cache.py:104` — `json.loads` menerima `bytes | str | list`
     dari Redis; diperbaiki dengan guard `isinstance`.
   - `mcp_server/domains/security.py:72` — `findings` tanpa anotasi tipe.
   - `mcp_server/domains/core.py:100` + `mcp_server/tools.py:149` —
     memanggil `provider_registry.list_providers` yang **tidak ada**
     (bug laten: selalu jatuh ke fallback mock). Diperbaiki memakai
     `default_registry().list_all()`.
4. **Review node — false positive "blocking" (fungsional).**
   Teks default `"Review: tidak ada temuan blocking."` mengandung kata
   `blocking` sehingga node review menandai satu temuan blocking di
   SETIAP run. Teks mock juga sama. Diperbaiki menjadi
   `"Review: tidak ada temuan."` + komentar peringatan di kode.
5. **`__main__.py` stub.** `python -m mufakat` hanya mencetak pesan
   "CLI belum tersedia" padahal CLI sudah ada. Diperbaiki: delegasikan
   ke `mufakat.cli:app`.

## Bug serius yang ditemukan saat audit run end-to-end

6. **Adapter CLI belum login menggantung graph tanpa batas.**
   `load_from_config` mengembalikan 5 adapter CLI (codex, copilot,
   antigravity, claude, opencode) hanya karena entrinya ada di
   `providers.yaml`. `_build_adapters` memakainya sebagai "nyata".
   Di VM ini `codex` ada di PATH tetapi `codex login status` =
   "Not logged in" — Codex CLI menggantung menunggu input interaktif
   dan graph macet di node `research` (faulthandler: event loop idle
   di `select`, CPU ~0, > 6 menit).
   Perbaikan:
   - `_build_adapters`: adapter CLI hanya dipakai bila
     `is_available()` benar (login terverifikasi, probe ≤ 5 detik).
   - `adapters/_cli.py`: `run_cli` dan `check_binary` memakai
     `stdin=DEVNULL` — CLI tidak pernah bisa menunggu input interaktif.
   - `_real_fn`: timeout 120 detik per panggilan adapter.
   - Test baru: `tests/test_cli_adapters.py`.
7. **Anti-loop tidak pernah terjadi (mutasi edge hilang).**
   `should_revise` mencatat `hash_history`/`finding_counts` dengan
   memutasi state DI DALAM edge function — mutasi edge tidak disimpan
   LangGraph ke checkpoint, sehingga riwayat selalu kosong dan loop
   audit→test→revise berjalan sampai cap `fix_iterations=5` (±19 detik).
   Perbaikan: pencatatan pindah ke node `test` (patch, tersimpan di
   checkpoint); `should_revise` jadi pure-read; hash dianggap berulang
   bila muncul ≥ 2x di riwayat. Setelah perbaikan: eskalasi di siklus
   ke-2, run mock selesai ±9 detik (graph) / ±12 detik (CLI penuh).
   Test diperbarui: `tests/test_anti_loop.py`.

## Konflik dependensi yang ditemukan

- **semgrep 1.186.0 membutuhkan `mcp==1.29.0`, fastmcp 4.2.2
  membutuhkan `mcp==2.3.0`.** Keduanya tidak bisa hidup di satu venv.
  Sempat terinstal semgrep (lalu `fastmcp` rusak: `mcp.server.
  request_state` tidak ada) — semgrep di-uninstall dari `.venv`,
  `mcp` dikembalikan ke 2.3.0, FastMCP jalan lagi. Keputusan
  (DECISIONS A12): venv utama memakai `mcp==2.3.0`; semgrep binary
  dijalankan dari venv/CI terpisah bila dibutuhkan. **Jangan instal
  semgrep ke `.venv` utama.**
- Konflik metadata `opentelemetry-api` (fastapi butuh ≥1.44.0,
  semgrep butuh ~=1.37.0) ikut hilang setelah semgrep di-uninstall.

## Catatan jujur lainnya

- **Bandit 56 Low** — sebagian besar `B404`/`B603` (subprocess),
  `B101` (assert), `B311` (random non-kriptografis). Semuanya Low dan
  sudah sesuai konteks (subprocess tanpa shell, allowlist, random
  hanya untuk label/seed). Tidak diubah.
- **`mufakat doctor` melaporkan `bandit`/`ruff` = TIDAK** karena doctor
  hanya memeriksa PATH sistem, bukan `.venv/bin`. Gate tetap memakai
  binary venv (lint/bandit lolos di run nyata). Keterbatasan doctor ini
  belum diperbaiki (di luar prioritas audit).
- **Satu run mock end-to-end (CLI)** setelah semua perbaikan:
  run `a22db95c`, ±12 detik, verdict **AMAN**, `diff/iter-01.patch`
  + 6 gate + worktree lengkap (lihat `runs/` di mesin uji — tidak
  ikut ke repo, di-gitignore).
- Verdict AMAN di atas HANYA berlaku untuk template todo yang
  dihasilkan mock — bukan klaim sistem ini aman secara umum.

## Cara mengulang audit ini

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/python -m mypy src/mufakat --ignore-missing-imports
.venv/bin/bandit -r src -x src/mufakat/web
mufakat doctor
```

## Audit putaran 2 — perbaikan (20 Nov 2026, 21:00 WIB, Python 3.12.3, pytest 9.2.0)

Audit: `AUDIT-AI-AGENT-PUTARAN-2-2026-11-20.md` (Claude, HEAD b4edfb3) + audit ulang ChatGPT (HEAD b4edfb3). Verdict sebelum perbaikan: kemajuan besar tapi masih TIDAK AMAN (1 Kritis, 6 Tinggi, 8 Sedang, 8 Rendah baru). Auditor putaran 2 mendapat `pytest -q` 3 failed, 171 passed, 1 skipped di mesin dengan CLI Docker tanpa daemon.

| Perintah | Hasil (benar-benar dijalankan, 21:00 WIB) |
|---|---|
| `pytest -q` (inti) | **242 passed, 1 skipped, 0 failed** (41,2 detik) |
| `pytest -q` (Local Runner) | **62 passed, 0 failed** |
| `npx vitest run` (ekstensi, dari laporan pekerja) | **59 passed** (13 engine + 20 audit-regressions + 26 audit-round2) |
| `npx wxt build` (ekstensi, dari laporan pekerja) | **berhasil, 7,4 dtk, 400,3 kB**; manifest tanpa `content_scripts`, tanpa `host_permissions` |
| `ruff check src tests mufakat-room/runner` | **bersih** |
| `mypy --check-untyped-defs src` | **bersih** (0 error, 96 file) |
| `docker --version` | **tidak ada di VM** — gate nyata berstatus **BELUM_TERVERIFIKASI** (fail-closed) |

Yang diperbaiki (per nomor audit): N1 gate periksa exit code per tool, output kosong/rusak = `tool-error`, Semgrep `--config /rules` + Trivy `--skip-db-update --offline-scan` di image, `--tmpfs /home/mufakat`; N7 deteksi daemon Docker nyata (`docker info` + `docker image inspect`); N2 `git add -A` + `git diff --cached HEAD` sebelum hash disetujui, commit tanpa `add -A`; N4 coverage ke mount terpisah di luar worktree, perubahan `conftest.py`/konfigurasi pytest = blocking; N3 `register_repo` hanya via CLI lokal, approval lewat kode 6 digit dialog OS; N8 `--yes` dihapus (non-interaktif hanya via `MUFAKAT_ALLOW_NONINTERACTIVE_APPROVE=1` + log); N12 hash kosong → tolak, verify+consume atomik; C3-sisa + GPT 1 `allowed_roots` dihapus dari parameter MCP, root wajib dari `MUFAKAT_WORKSPACE_ROOTS`, tolak HOME; GPT 5 authorization layer umum sebelum tool MCP dijalankan, Git dibatasi registry; N5 labelMap per ronde di Dexie, winner dipetakan ke proposal benar; N6 satu sumber kebenaran state + event `reset` + `ronde_baru`; N10 ID Muse disamakan jadi `muse`; N13 delimiter anti prompt-injection; N14 pola `glpat-`/`hf_` (TS + Python); GPT 4 secret scan sebelum simpan; GPT 6 baca/isi DOM dihapus dari MVP (content script pindah ke `src/phase2-optin/`); GPT 7 gate Node khusus; GPT 8 CI `.github/workflows/ci.yml` (file lokal — tidak bisa di-push via API, lihat README); N9 wrapper executable + console script venv; N11 `interrupt()` LangGraph; L4 prompt CLI dengan `--`; L5 patch applier jaga CRLF/tanpa newline akhir.

Yang masih tersisa: build image Docker belum terverifikasi (tidak ada Docker di VM); selector situs AI belum terverifikasi di situs asli; uji klik side panel end-to-end di Chrome sungguhan belum dilakukan; UI App.tsx untuk alur approval runner (kode 6 digit) belum disambungkan — helper `runnerClient.ts` sudah ada; penolakan `interrupt()` belum menghentikan graph di level edge; pola `jwt_token` di secret scanner TS belum ada di Python; DB Trivy membeku pada tanggal build (perlu rebuild berkala).
