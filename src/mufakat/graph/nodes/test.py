"""Node test (T7): jalankan gate pytest atas worktree.

Memakai ``gates.pytest.run`` bila worktree tersedia; bila tidak,
temuan test dikosongkan (bukan gagal). Hasil dicatat di messages.

Node ini JUGA mencatat riwayat anti-loop sebagai patch
(``hash_history`` + ``finding_counts``): pencatatan HARUS di node,
karena mutasi di dalam edge function LangGraph tidak disimpan ke
checkpoint (ditemukan 20 Nov 2026 — riwayat yang dicatat di edge
selalu hilang, sehingga eskalasi hash tidak pernah terjadi).
"""

from __future__ import annotations

try:
    from .common import append_message
except ImportError:  # pragma: no cover
    from common import append_message  # type: ignore


async def node(state, adapters=None, ctx=None):
    """Test -> patch state."""
    ctx = ctx or {}
    worktree = ctx.get("worktree")
    findings = list(getattr(state, "findings", []) or [])
    if worktree:
        try:
            from mufakat.gates.pytest import run as run_pytest
        except ImportError:
            try:
                from mufakat.gates.pytest import run as run_pytest  # type: ignore
            except ImportError:
                run_pytest = None  # type: ignore[assignment]
        if run_pytest is not None:
            try:
                result = run_pytest(worktree)
            except Exception:
                result = None
            if result is not None:
                ctx["pytest_result"] = result
                findings = [f for f in findings if f.get("tool") != "pytest"]
                for finding in getattr(result, "findings", []) or []:
                    findings.append(dict(finding))
                status = "lolos" if getattr(result, "passed", False) else "gagal"
                text = f"Test selesai: gate pytest {status}."
            else:
                text = "Test selesai: gate pytest tidak dapat dijalankan."
        else:
            text = "Test selesai: modul gate pytest tidak tersedia."
    else:
        text = "Test selesai: tidak ada worktree, tidak ada test dijalankan."
    messages = append_message(state, "tester", text)
    # Riwayat anti-loop (patch — disimpan LangGraph ke checkpoint).
    try:
        from mufakat.graph.edges import current_hash
    except ImportError:  # pragma: no cover
        try:
            from ..edges import current_hash  # type: ignore
        except ImportError:
            current_hash = None  # type: ignore[assignment]
    patch: dict = {"messages": messages, "findings": findings,
                   "phase": "revise"}
    if current_hash is not None:
        history = list(getattr(state, "hash_history", []) or [])
        history.append(current_hash(state, findings))
        counts = list(getattr(state, "finding_counts", []) or [])
        counts.append(len(findings))
        patch["hash_history"] = history
        patch["finding_counts"] = counts
    return patch
