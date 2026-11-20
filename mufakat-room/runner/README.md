# MUFAKAT Room — Local Runner (Python)

Native messaging host + worktree + sandbox Docker + gates + verdict + server MCP
(Claude §5, §T11–T15).

> **Status:** kode Python runner selesai dan diuji unit (lihat `tests/`).
> Docker sandbox **belum terverifikasi** di VM ini (binary `docker` tidak ada)
> — `sandbox.run_in_sandbox` mengembalikan `verified: false` bila Docker
> tidak tersedia, bukan pura-pura jalan.

## Instalasi

```bash
cd mufakat-room/runner
python -m venv .venv
source .venv/bin/activate
pip install -e .
# Opsional (server MCP): pip install -e ".[mcp]"
# Opsional (reuse gates/sandbox MUFAKAT inti): instal paket `mufakat` juga.
```

## Daftarkan sebagai Native Messaging Host

```bash
python install_host.py --extension-id chrome-extension://<ID_EKSTENSI>/ --dry-run
python install_host.py --extension-id chrome-extension://<ID_EKSTENSI>/
```

Hanya ID ekstensi itu yang boleh terhubung (`allowed_origins`). Host tidak
membuka port jaringan apa pun.

## Jalankan host (dipanggil Chrome, bukan manual)

```bash
python -m mufakat_runner.host
```

Protokol: stdin/stdout length-prefixed JSON (4 byte little-endian + JSON).

Perintah: `init_workspace`, `apply_files`, `run_gates`, `diff`, `commit`,
`cleanup`, `status`. `commit` HANYA jalan dengan approval token sekali pakai
dari UI — tanpa token, ditolak. Push tidak pernah dilakukan.

## Server MCP (opsional)

```bash
mufakat-room-mcp
```

Tool: `room_status`, `gate_report`, `run_gates`. Butuh `fastmcp`; bila belum
terpasang, ketiga fungsi tetap bisa diimpor sebagai fungsi Python biasa.

## Test

```bash
python -m pytest tests/ -q
```

## Reuse (satu sumber kebenaran, tanpa duplikasi membabi buta)

| Runner | Reuse dari MUFAKAT inti (`mufakat.*`) | Fallback lokal |
|---|---|---|
| `worktree.init_workspace` / `cleanup` | `mufakat.sandbox.worktree` | folder biasa |
| `sandbox.run_in_sandbox` / `build_image` | `mufakat.sandbox.docker` | `verified: false`, exit 127 |
| `gates.run_gates` | `mufakat.gates.runner.run_all` | — (wajib; error bila paket tidak ada) |
| `verdict.apply_verdict` | `mufakat.gates.verdict.verdict` | — (wajib; error bila paket tidak ada) |
| `worktree.apply_files` (validasi path) | — (selalu lokal) | tolak `..` / absolut |
| `host` (native messaging) | — (baru, khusus Room) | — |

## Keamanan

- Path traversal ditolak sebelum file apa pun ditulis (`../../etc/passwd` → error).
- Commit butuh approval token sekali pakai; push tidak pernah otomatis.
- Kode AI tidak pernah dijalankan langsung di laptop — hanya di container Docker
  non-root, `--network none` saat test, CPU/RAM/waktu dibatasi.
- Tidak ada auto-send / otomasi situs AI di runner ini.
