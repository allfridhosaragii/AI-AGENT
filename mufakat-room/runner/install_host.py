"""Daftarkan Local Runner sebagai Chrome Native Messaging Host.

Menulis file manifest host ``com.mufakat.runner.json`` ke lokasi standar
OS (Linux/macOS/Windows) dan — di Windows — menulis registry key yang
menunjuk ke file manifest itu (audit H6: dulu skrip hanya MENCETAK
instruksi registry tanpa menulis apa pun).

``path`` di manifest HARUS menunjuk ke skrip wrapper executable
(``mufakat-runner-host`` / ``mufakat-runner-host.bat`` di Windows),
BUKAN ke ``sys.executable`` (audit H6: Chrome menjalankan ``path``
dengan argumen ``chrome-extension://<id>/``, sehingga Python
mencoba membuka file bernama itu dan langsung keluar).

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
import shutil
import sys
from pathlib import Path

HOST_NAME = "com.mufakat.runner"

# ID ekstensi Chrome: 32 huruf kecil a-p (bentuk kanonik), tapi validasi
# di sini sengaja longgar ke [a-z0-9]+ agar ID pengembangan/uji tetap
# bisa dipakai — yang ditolak adalah ID kosong, huruf besar, dan
# segmen path tambahan (dulu "chrome-extension://abc/extra" dan
# "chrome-extension://" lolos begitu saja).
_EXTENSION_ID_RE = re.compile(r"^chrome-extension://[a-z0-9]+/$")


def default_host_path() -> str:
    """Path executable host (H6, N9).

    Urutan (audit N9: SELALU pakai console script dari venv, path
    absolut — bukan ``python3`` dari PATH, dan bukan wrapper yang
    memanggil interpreter sembarang):

    1. Console script ``mufakat-runner-host`` di venv yang sama dengan
       interpreter yang menjalankan skrip ini (``sys.prefix/bin``) —
       path absolut, venv terbawa.
    2. Console script yang sama di PATH (``shutil.which``) — path absolut.
    3. Skrip wrapper di samping file ini (fallback bila paket belum
       terinstal) — harus executable.
    TIDAK PERNAH sys.executable.
    """
    import os as _os

    bin_dir = Path(sys.executable).resolve().parent
    venv_script = bin_dir / (
        "mufakat-runner-host.bat" if sys.platform.startswith("win")
        else "mufakat-runner-host")
    if venv_script.is_file() and _os.access(venv_script, _os.X_OK):
        return str(venv_script.resolve())
    installed = shutil.which("mufakat-runner-host")
    if installed:
        return str(Path(installed).resolve())
    here = Path(__file__).resolve().parent
    if sys.platform.startswith("win"):
        candidate = here / "mufakat-runner-host.bat"
    else:
        candidate = here / "mufakat-runner-host"
    if candidate.is_file():
        return str(candidate.resolve())
    raise ValueError(
        "Wrapper host tidak ditemukan: instal paket runner "
        "(pip install -e mufakat-room/runner) atau buat skrip "
        "mufakat-runner-host di samping install_host.py.")


def host_manifest(extension_id: str, host_path: str) -> dict:
    """Bangun isi manifest native messaging host."""
    if not isinstance(extension_id, str) or not _EXTENSION_ID_RE.match(extension_id):
        raise ValueError(
            "extension-id harus berbentuk 'chrome-extension://<id>/' "
            "(id huruf kecil/angka, diakhiri '/')."
        )
    if not isinstance(host_path, str) or not host_path.strip():
        raise ValueError("host-path tidak boleh kosong.")
    if not Path(host_path).is_absolute():
        raise ValueError(
            "host-path harus path absolut (N9: console script venv, "
            "bukan nama relatif / dari PATH).")
    if host_path == sys.executable:
        raise ValueError(
            "host-path tidak boleh sys.executable (interpreter Python): "
            "path harus menunjuk ke skrip wrapper executable "
            "(mufakat-runner-host).")
    return {
        "name": HOST_NAME,
        "description": "MUFAKAT Room Local Runner (worktree + gates lokal).",
        "path": host_path,
        "type": "stdio",
        "allowed_origins": [extension_id],
    }


def default_manifest_dir() -> Path:
    """Lokasi manifest host menurut OS (Linux/macOS/Windows)."""
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts"
    if sys.platform.startswith("win"):
        return (Path.home() / "AppData" / "Local" / "Google" / "Chrome"
                / "User Data" / "NativeMessagingHosts")
    return Path.home() / ".config/google-chrome/NativeMessagingHosts"


def _write_windows_registry(manifest_path: Path) -> None:
    """Tulis registry key Chrome NativeMessagingHosts (Windows, H6).

    Key: HKEY_CURRENT_USER\\Software\\Google\\Chrome\\
    NativeMessagingHosts\\com.mufakat.runner -> (Default) = path manifest.
    """
    import winreg

    key_path = (r"Software\Google\Chrome\NativeMessagingHosts"
                rf"\{HOST_NAME}")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path))


def install(extension_id: str, host_path: str | None = None,
            manifest_dir: Path | None = None,
            dry_run: bool = False) -> Path:
    """Tulis manifest; kembalikan jalurnya.

    Windows: manifest ditulis ke file DAN registry key ditulis
    (bukan hanya dicetak). ``host_path=None`` memakai wrapper default.
    """
    resolved_host_path = host_path or default_host_path()
    manifest = host_manifest(extension_id, resolved_host_path)
    target_dir = manifest_dir or default_manifest_dir()
    target = target_dir / f"{HOST_NAME}.json"
    if dry_run:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        print(f"[dry-run] Manifest akan ditulis ke: {target}")
        if sys.platform.startswith("win"):
            print("[dry-run] Registry key Windows akan ditulis ke "
                  r"HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts"
                  rf"\{HOST_NAME}")
        return target
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifest host ditulis ke: {target}")
    if sys.platform.startswith("win"):
        _write_windows_registry(target)
        print("Registry key Windows ditulis: "
              r"HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts"
              rf"\{HOST_NAME} = {target}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daftarkan MUFAKAT Room native host.")
    parser.add_argument("--extension-id", required=True,
                        help="ID ekstensi, mis. chrome-extension://abcdef.../")
    parser.add_argument("--host-path", default=None,
                        help="Path executable host (default: wrapper mufakat-runner-host).")
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
