"""Titik masuk ``python -m mufakat`` — delegasikan ke CLI Typer.

CLI lengkap ada di ``mufakat.cli`` (entry point ``mufakat`` di
``pyproject.toml``); modul ini hanya meneruskan argv yang sama.
"""

from __future__ import annotations

from mufakat.cli import app


def main() -> None:
    """Jalankan CLI MUFAKAT."""
    app()


if __name__ == "__main__":
    main()
