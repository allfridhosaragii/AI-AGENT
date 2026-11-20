"""Titik masuk ``python -m mufakat``.

Modul ini sengaja tidak mengimpor ``mufakat.cli`` secara langsung agar
paket tetap bisa diimpor sebelum CLI (T3) selesai dibuat. CLI lengkap
disediakan lewat entry point ``mufakat`` pada ``pyproject.toml``.
"""

from mufakat import __version__


def main() -> None:
    """Tampilkan versi dan petunjuk singkat."""
    print(f"MUFAKAT {__version__}")
    print("Jalankan perintah CLI lewat entry point 'mufakat' setelah modul CLI tersedia.")


if __name__ == "__main__":
    main()
