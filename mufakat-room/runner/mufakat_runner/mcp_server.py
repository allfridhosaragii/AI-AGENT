"""Server MCP Local Runner (Claude §5, §T15 — opsional, Fase 4).

Tool: ``room_status``, ``gate_report``, ``run_gates``.

Bila ``fastmcp`` terpasang, tool didaftarkan ke server FastMCP bernama
``mufakat-room`` (transport stdio, ``main()``). Bila tidak terpasang,
ketiga fungsi tetap bisa diimpor dan dipanggil langsung sebagai fungsi
Python biasa — server MCP dinyatakan "belum terverifikasi" sampai
diuji dengan MCP Inspector.
"""

from __future__ import annotations

import json
from pathlib import Path

from mufakat_runner import gates as gates_mod
from mufakat_runner import verdict as verdict_mod

__all__ = ["room_status", "gate_report", "run_gates", "main"]


def room_status(room_dir: str = "runs/room-mock") -> dict:
    """Status room dari ``room.json`` (bila ada); tanpa itu, status jujur."""
    room_file = Path(room_dir) / "room.json"
    if not room_file.is_file():
        room_file = Path(room_dir) / "room" / "room.json"
    if not room_file.is_file():
        return {
            "ok": True,
            "room_found": False,
            "mode": "manual_handoff",
            "note": "Tidak ada room.json di path tersebut (belum ada run Room).",
        }
    try:
        data = json.loads(room_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "room_found": False, "error": f"room.json rusak: {exc}"}
    if not isinstance(data, dict):
        return {"ok": False, "room_found": False, "error": "room.json rusak: isi harus object."}
    return {
        "ok": True,
        "room_found": True,
        "room_id": data.get("room_id"),
        "state": data.get("state"),
        "round_no": data.get("round_no"),
        "providers": data.get("providers"),
        "responses_imported": len(data.get("responses", [])),
        "mode": data.get("mode", "manual_handoff"),
    }


def run_gates(target_dir: str = ".", profile: str = "python") -> dict:
    """Jalankan gates + verdict; kembalikan hasil terstruktur."""
    if not isinstance(target_dir, str) or not isinstance(profile, str):
        return {"ok": False, "error": "target_dir dan profile harus string."}
    results = gates_mod.run_gates(target_dir, profile=profile)
    return {"ok": True, "results": results, "verdict": verdict_mod.apply_verdict(results)}


def gate_report(run_dir: str = ".") -> dict:
    """Baca ``gates/verdict.json`` hasil run sebelumnya (bila ada)."""
    verdict_file = Path(run_dir) / "gates" / "verdict.json"
    if not verdict_file.is_file():
        return {
            "ok": True,
            "found": False,
            "status": "belum terverifikasi",
            "note": "Belum ada gates/verdict.json di run tersebut.",
        }
    try:
        data = json.loads(verdict_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "found": False, "error": f"verdict.json rusak: {exc}"}
    if not isinstance(data, dict):
        return {"ok": False, "found": False, "error": "verdict.json rusak: isi harus object."}
    return {"ok": True, "found": True, "verdict": data}


def main() -> None:
    """Jalankan server MCP via stdio (butuh fastmcp terpasang)."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "fastmcp tidak terpasang di environment ini — server MCP runner "
            "belum terverifikasi. Instal fastmcp atau panggil fungsi "
            "room_status/gate_report/run_gates langsung."
        ) from exc

    mcp = FastMCP("mufakat-room")
    mcp.tool()(room_status)
    mcp.tool()(gate_report)
    mcp.tool()(run_gates)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
