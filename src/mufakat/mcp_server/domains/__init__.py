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

    Setiap ``mcp.tool(fn)`` di dalam ``register()`` domain dibungkus
    dulu oleh authorization layer (GPT 5): permission dari
    ``CONTRACTS`` ditegakkan SEBELUM tool dijalankan. Pembungkusan
    dilakukan dengan menukar ``mcp.tool`` sementara di sini supaya
    semua domain — termasuk yang ditambahkan nanti — otomatis
    terlindungi tanpa mengubah tiap ``register()``.

    Mengembalikan daftar nama tool yang terdaftar.
    """
    import importlib

    from mufakat.mcp_server.authorization import authorize, permission_for

    real_tool = mcp.tool

    def guarded_tool(fn=None, **kwargs):
        # Dipakai sebagai mcp.tool(fn) di semua domain.
        if fn is None:
            return real_tool(**kwargs)
        return real_tool(authorize(fn, permission_for(fn.__name__)), **kwargs)

    mcp.tool = guarded_tool
    try:
        names: list[str] = []
        for domain in DOMAINS:
            module = importlib.import_module(f".{domain}", __package__)
            names.extend(module.register(mcp))
        return names
    finally:
        mcp.tool = real_tool


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
