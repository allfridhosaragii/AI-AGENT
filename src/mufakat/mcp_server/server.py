"""Server MCP MUFAKAT — SATU server FastMCP bernama ``mufakat`` (gateway).

Transport: stdio (``mcp.run(transport="stdio")`` di :func:`main`).

Semua tool hidup di 15 modul domain di
``mufakat.mcp_server.domains`` (ChatGPT §7): core, communication,
meeting, task, memory, project, git, filesystem, terminal, testing,
security, research, evaluation, approval, observability. Modul ini
hanya membuat server, mendaftarkan semua domain, dan mengekspor
kembali fungsi-fungsi lama agar pemanggil lama (test, CLI) tetap
jalan. Tidak ada logika tool di sini.

Keamanan: tools tulis/eksekusi/Git/jaringan butuh permission ketat
(lihat ``CONTRACTS`` tiap domain); ``terminal_run`` hanya allowlist
(``echo``/``ls``/``pytest``, tanpa shell, tolak metakarakter);
``filesystem_read`` menolak file rahasia; secret tidak pernah masuk
log/laporan.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mufakat.mcp_server.domains import contracts, register_all
from mufakat.mcp_server.domains.approval import (
    approval_get_status,
    approval_record_decision,
    approval_request,
)
from mufakat.mcp_server.domains.communication import (
    agent_send_message,
    message_list,
)
from mufakat.mcp_server.domains.core import (
    agent_get_capabilities,
    agent_register,
    core_list_agents,
    debate_start,
    debate_status,
    gate_report,
    pipeline_run,
)
from mufakat.mcp_server.domains.evaluation import (
    evaluation_submit,
    review_approve,
    review_list,
    review_submit,
)
from mufakat.mcp_server.domains.filesystem import (
    filesystem_propose_patch,
    filesystem_read,
)
from mufakat.mcp_server.domains.git import (
    git_branch,
    git_commit,
    git_create_worktree,
    git_diff,
    git_status,
)
from mufakat.mcp_server.domains.meeting import (
    meeting_create,
    meeting_get,
    meeting_record_decision,
    meeting_submit_argument,
    meeting_submit_critique,
    meeting_submit_rebuttal,
    meeting_submit_revision,
)
from mufakat.mcp_server.domains.memory import (
    memory_list,
    memory_read,
    memory_write,
)
from mufakat.mcp_server.domains.observability import (
    observability_list_runs,
    observability_status,
)
from mufakat.mcp_server.domains.project import (
    project_create,
    project_create_adr,
    project_get_context,
)
from mufakat.mcp_server.domains.research import (
    research_list_references,
    research_save_reference,
    research_search,
)
from mufakat.mcp_server.domains.security import (
    security_get_findings,
    security_scan,
    security_scan_dependencies,
    security_scan_secrets,
)
from mufakat.mcp_server.domains.task import (
    task_assign,
    task_create,
    task_get,
    task_get_dependencies,
    task_update_status,
)
from mufakat.mcp_server.domains.terminal import terminal_run
from mufakat.mcp_server.domains.testing import (
    test_get_results,
    test_run_e2e,
    test_run_unit,
    testing_run,
)

mcp = FastMCP("mufakat")
REGISTERED_TOOLS = register_all(mcp)


def list_tool_contracts() -> list[dict]:
    """Kontrak semua tool: nama, domain, deskripsi, permission, scope."""
    return contracts()


def main() -> None:
    """Entry point console script ``mufakat-mcp``: jalankan server via stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

__all__ = [
    "mcp", "REGISTERED_TOOLS", "list_tool_contracts", "main",
    "debate_start", "debate_status", "pipeline_run", "gate_report",
    "core_list_agents", "agent_register", "agent_get_capabilities",
    "agent_send_message", "message_list",
    "meeting_create", "meeting_submit_argument", "meeting_submit_critique",
    "meeting_submit_rebuttal", "meeting_submit_revision",
    "meeting_record_decision", "meeting_get",
    "task_create", "task_assign", "task_update_status",
    "task_get_dependencies", "task_get",
    "memory_write", "memory_read", "memory_list",
    "project_create", "project_get_context", "project_create_adr",
    "git_status", "git_diff", "git_branch", "git_create_worktree",
    "git_commit",
    "filesystem_read", "filesystem_propose_patch",
    "terminal_run",
    "testing_run", "test_run_unit", "test_run_e2e", "test_get_results",
    "security_scan", "security_scan_secrets", "security_scan_dependencies",
    "security_get_findings",
    "research_search", "research_save_reference", "research_list_references",
    "evaluation_submit", "review_submit", "review_approve", "review_list",
    "approval_request", "approval_get_status", "approval_record_decision",
    "observability_status", "observability_list_runs",
]
