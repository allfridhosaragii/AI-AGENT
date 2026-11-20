"""Domain core — registrasi agent, kapabilitas, debat, pipeline, gate.

Permission: ``read`` untuk status/daftar, ``write-sandbox`` untuk
memulai run (run hanya menulis ke ``runs/<run_id>/`` miliknya).
"""

from __future__ import annotations

from mufakat.mcp_server.tools import (
    create_run_for_mcp,
    err,
    gate_report_for_run,
    list_agents,
    ok,
)
from mufakat.runner import read_run

from . import store

DOMAIN = "core"

CONTRACTS = [
    {"name": "debate_start", "description": "Mulai debat baru tentang sebuah topik.",
     "permission": "write-sandbox", "scope": "runs"},
    {"name": "debate_status", "description": "Status satu run debat.",
     "permission": "read", "scope": "runs"},
    {"name": "pipeline_run", "description": "Jalankan pipeline dari spec dan/atau repo.",
     "permission": "write-sandbox", "scope": "runs"},
    {"name": "gate_report", "description": "Laporan gate satu run.",
     "permission": "read", "scope": "runs"},
    {"name": "core_list_agents", "description": "Daftar agen yang terdaftar.",
     "permission": "read", "scope": "agents"},
    {"name": "agent_register", "description": "Daftarkan definisi agen baru.",
     "permission": "write-sandbox", "scope": "agents"},
    {"name": "agent_get_capabilities", "description": "Kapabilitas satu provider/agent.",
     "permission": "read", "scope": "agents"},
]


def debate_start(topic: str) -> str:
    """Mulai debat baru tentang sebuah topik. Mengembalikan run_id."""
    result = create_run_for_mcp(topic, provider="mock", mode="debate")
    return str(result["run_id"])


def debate_status(run_id: str) -> dict:
    """Status satu run debat (baca runs/<run_id>/)."""
    info = read_run(run_id)
    if info is None:
        return err("Run tidak ditemukan.", run_id=run_id)
    info.pop("messages", None)
    return ok(**info)


def pipeline_run(spec_path: str = "", repo_path: str = "") -> dict:
    """Jalankan pipeline dari file spec dan/atau repo."""
    from mufakat.mcp_server.tools import read_file_safe

    idea = ""
    if spec_path:
        read = read_file_safe(spec_path)
        if not read.get("ok"):
            return err("Spec tidak bisa dibaca.", spec_path=spec_path,
                       detail=read.get("error", ""))
        idea = str(read.get("content", ""))[:4000]
    if not idea:
        idea = f"Pipeline untuk repo: {repo_path or '.'}"
    result = create_run_for_mcp(idea, provider="mock", mode="pipeline")
    return ok(run_id=result["run_id"], status=result["status"],
              dir=result["dir"], spec_path=spec_path, repo_path=repo_path)


def gate_report(run_id: str) -> dict:
    """Laporan gate satu run; belum terverifikasi bila tidak ada hasil gate."""
    return gate_report_for_run(run_id)


def core_list_agents() -> dict:
    """Daftar agen yang terdaftar (mock bila registry belum terisi)."""
    registered = list(store.agents.values())
    if registered:
        return ok(agents=registered, count=len(registered))
    return list_agents()


def agent_register(agent_id: str, role: str, provider: str = "mock",
                   model: str = "") -> dict:
    """Daftarkan definisi agen baru (role + provider + model opsional)."""
    if not agent_id or not role:
        return err("agent_id dan role wajib diisi.")
    record = {"agent_id": agent_id, "role": role, "provider": provider,
              "model": model}
    store.agents[agent_id] = record
    return ok(**record)


def agent_get_capabilities(agent_id: str) -> dict:
    """Kapabilitas satu provider/agent dari provider registry."""
    if agent_id in store.agents:
        record = dict(store.agents[agent_id])
        record["capabilities"] = ["text_generation"]
        return ok(**record)
    try:
        from mufakat.provider_registry import default_registry
    except ImportError:  # pragma: no cover - registry selalu ada
        default_registry = None  # type: ignore[assignment]
    providers = [p.name for p in default_registry().list_all()] \
        if default_registry is not None else []
    if agent_id in providers:
        return ok(agent_id=agent_id, provider=agent_id,
                  capabilities=["text_generation"])
    return err("Agent/provider tidak dikenal.", agent_id=agent_id)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain core ke ``mcp``."""
    for fn in (debate_start, debate_status, pipeline_run, gate_report,
               core_list_agents, agent_register, agent_get_capabilities):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
