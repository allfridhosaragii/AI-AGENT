"""Daftarkan Local Runner sebagai Chrome Native Messaging Host.

Menulis file manifest host ``com.mufakat.runner.json`` ke lokasi standar
OS (Linux/macOS) dan mencetak instruksi untuk Windows (registry).

Manifest membatasi ``allowed_origins`` HANYA ke ID ekstensi yang
diberikan (``--extension-id``). Tanpa ID ekstensi yang benar, Chrome
menolak koneksi — runner tidak menerima perintah dari sembarang halaman.

Penggunaan:
    python install_host.py --extension-id chrome-extension://<ID>/
    python install_host.py --extension-id chrome-extension://<ID>/ --dry-run

``--dry-run`` hanya mencetak manifest tanpa menulis file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HOST_NAME = "com.mufakat.runner"

# ID ekstensi Chrome: 32 huruf kecil a-p (bentuk kanonik), tapi validasi
# di sini sengaja longgar ke [a-z0-9]+ agar ID pengembangan/uji tetap
# bisa dipakai — yang ditolak adalah ID kosong, huruf besar, dan
# segmen path tambahan (dulu "chrome-extension://abc/extra" dan
# "chrome-extension://" lolos begitu saja).
_EXTENSION_ID_RE = re.compile(r"^chrome-extension://[a-z0-9]+/$")


def host_manifest(extension_id: str, host_path: str) -> dict:
    """Bangun isi manifest native messaging host."""
    if not isinstance(extension_id, str) or not _EXTENSION_ID_RE.match(extension_id):
        raise ValueError(
            "extension-id harus berbentuk 'chrome-extension://<id>/' "
            "(id huruf kecil/angka, diakhiri '/')."
        )
    if not isinstance(host_path, str) or not host_path.strip():
        raise ValueError("host-path tidak boleh kosong.")
    return {
        "name": HOST_NAME,
        "description": "MUFAKAT Room Local Runner (worktree + gates lokal).",
        "path": host_path,
        "type": "stdio",
        "allowed_origins": [extension_id],
    }


def default_manifest_dir() -> Path:
    """Lokasi manifest host menurut OS (Linux/macOS)."""
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts"
    return Path.home() / ".config/google-chrome/NativeMessagingHosts"


def install(extension_id: str, host_path: str, manifest_dir: Path | None = None,
            dry_run: bool = False) -> Path:
    """Tulis manifest; kembalikan jalurnya. Windows: cetak instruksi registry."""
    manifest = host_manifest(extension_id, host_path)
    target_dir = manifest_dir or default_manifest_dir()
    target = target_dir / f"{HOST_NAME}.json"
    if sys.platform.startswith("win"):
        print("Windows: tulis registry key")
        print(r"  HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\com.mufakat.runner")
        print(f"  (Default) = {target}")
    if dry_run:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        print(f"[dry-run] Manifest akan ditulis ke: {target}")
        return target
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifest host ditulis ke: {target}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daftarkan MUFAKAT Room native host.")
    parser.add_argument("--extension-id", required=True,
                        help="ID ekstensi, mis. chrome-extension://abcdef.../")
    parser.add_argument("--host-path", default=sys.executable,
                        help="Path executable host (default: python saat ini).")
    parser.add_argument("--manifest-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    install(
        args.extension_id,
        args.host_path,
        Path(args.manifest_dir) if args.manifest_dir else None,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
