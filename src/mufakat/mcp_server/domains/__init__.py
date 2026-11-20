"""Registry 15 domain MCP MUFAKAT (ChatGPT §7).

Satu server FastMCP bernama ``mufakat`` tetap menjadi gateway
tunggal (transport stdio). Tiap domain adalah modul terpisah di
paket ini dan mendaftarkan tool-nya sendiri lewat ``register(mcp)``.

Daftar domain: core, communication, meeting, task, memory, project,
git, filesystem, terminal, testing, security, research, evaluation,
approval, observability.
"""

from __future__ import annotations

DOMAINS = (
    "core",
    "communication",
    "meeting",
    "task",
    "memory",
    "project",
    "git",
    "filesystem",
    "terminal",
    "testing",
    "security",
    "research",
    "evaluation",
    "approval",
    "observability",
)


def register_all(mcp) -> list[str]:
    """Daftarkan semua tool dari 15 domain ke ``mcp``.

    Mengembalikan daftar nama tool yang terdaftar.
    """
    import importlib

    names: list[str] = []
    for domain in DOMAINS:
        module = importlib.import_module(f".{domain}", __package__)
        names.extend(module.register(mcp))
    return names


def contracts() -> list[dict]:
    """Kontrak semua tool: nama, deskripsi, permission, scope."""
    import importlib

    out: list[dict] = []
    for domain in DOMAINS:
        module = importlib.import_module(f".{domain}", __package__)
        for contract in getattr(module, "CONTRACTS", []):
            out.append({"domain": domain, **contract})
    return out


__all__ = ["DOMAINS", "register_all", "contracts"]
