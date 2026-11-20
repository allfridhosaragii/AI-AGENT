# SELF_AUDIT.md — Audit mandiri kode MUFAKAT sendiri

Tanggal: **20 Nov 2026**. Perintah: jalankan tool gate yang tersedia di
VM ini pada kode MUFAKAT sendiri, simpan hasilnya, perbaiki temuan yang
nyata dan aman diperbaiki. Yang tidak tersedia dicatat sebagai
**belum terverifikasi** — bukan "lolos".

## Ringkasan hasil

| Tool | Hasil | Keterangan |
|---|---|---|
| `pytest -q` | **71 passed, 1 skipped, 0 failed** (86 detik) | 1 skip = catatan Playwright belum terpasang |
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
