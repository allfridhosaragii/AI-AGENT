"""Node test (T7): jalankan gate pytest atas worktree.

Memakai ``gates.pytest.run`` bila worktree tersedia; bila tidak,
temuan test dikosongkan (bukan gagal). Hasil dicatat di messages.
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
                run_pytest = None
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
    return {"messages": messages, "findings": findings, "phase": "revise"}
