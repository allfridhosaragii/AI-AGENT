"""Shared helpers for CLI-based adapters (T4).

All CLI adapters run via ``asyncio.create_subprocess_exec`` (no shell),
with ``cwd``/``timeout`` taken from ``ctx``.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess

from .base import AdapterError, Reply

_TEXT_FIELDS = ("text", "output", "result", "response", "content")


def _extract_text(raw: str) -> str:
    """Pull the reply text out of raw stdout.

    Tries JSON first (fields ``text``/``output``/``result``/``response``/
    ``content``, including nested ``{"result": {...}}``), falls back to
    the raw string.
    """
    raw = raw.strip()
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in _TEXT_FIELDS:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                for sub in _TEXT_FIELDS:
                    inner = value.get(sub)
                    if isinstance(inner, str) and inner.strip():
                        return inner
        # Some CLIs emit {"type": "result", "result": "..."} etc.
        for value in data.values():
            if isinstance(value, str) and value.strip():
                return value
    return raw


async def run_cli(name: str, family: str, cmd: list[str],
                  ctx: dict | None) -> Reply:
    """Run a CLI command and return its Reply. Raises AdapterError."""
    ctx = ctx or {}
    cwd = ctx.get("cwd")
    timeout = float(ctx.get("timeout", 300))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise AdapterError(f"{name}: binary not found: {cmd[0]}") from exc
    except OSError as exc:
        raise AdapterError(f"{name}: failed to start: {exc}") from exc

    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise AdapterError(f"{name}: timed out after {timeout}s") from exc

    stdout = out.decode("utf-8", errors="replace")
    stderr = err.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise AdapterError(
            f"{name}: exit {proc.returncode}: {stderr.strip()[:500]}")
    text = _extract_text(stdout)
    return Reply(text=text, usage={"tokens_in": 0, "tokens_out": 0,
                                   "cost_usd": 0.0},
                 provider=name, family=family, raw=stdout)


def check_binary(binary: str, probe: list[str] | None = None,
                 timeout: int = 5) -> bool:
    """Return True iff *binary* is on PATH and (if *probe* given) the
    probe command exits 0 within *timeout* seconds. Never raises."""
    try:
        if shutil.which(binary) is None:
            return False
        if probe is None:
            return True
        result = subprocess.run(
            probe, capture_output=True, timeout=timeout)
        return result.returncode == 0
    except Exception:
        return False
