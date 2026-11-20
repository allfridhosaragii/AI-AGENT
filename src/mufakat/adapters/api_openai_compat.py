"""OpenAI-compatible HTTP adapter (T3).

Talks to any ``/chat/completions`` endpoint (DeepSeek, Qwen, OpenAI,
local OpenAI-compatible servers, ...).  Uses ``httpx``; an explicit
``http_client`` can be injected for tests/mocking.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import yaml

from .base import Adapter, AdapterError, Reply

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OpenAICompatAdapter(Adapter):
    """Adapter over an OpenAI-compatible ``/chat/completions`` API."""

    def __init__(self, name: str, family: str, base_url: str,
                 api_key: str, model: str,
                 http_client: httpx.AsyncClient | None = None):
        self.name = name
        self.family = family
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = http_client

    # -- availability -------------------------------------------------
    def is_available(self) -> bool:
        # No local binary/login to check; availability = credentials + url.
        return bool(self.base_url and self.model and self.api_key)

    # -- ask ----------------------------------------------------------
    async def ask(self, prompt: str, system: str = "",
                  ctx: dict | None = None) -> Reply:
        ctx = ctx or {}
        timeout = float(ctx.get("timeout", 120))
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.model, "messages": messages}

        client = self._client
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=timeout)
        assert client is not None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            last_error: Exception | None = None
            for attempt in range(3):  # initial + 2 retries
                try:
                    resp = await client.post(url, json=body, headers=headers)
                except httpx.TimeoutException:
                    last_error = AdapterError(
                        f"{self.name}: request timed out after {timeout}s")
                    break
                except httpx.HTTPError as exc:
                    # Network-level error: retry with backoff.
                    last_error = AdapterError(f"{self.name}: {exc}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    break

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except ValueError as exc:
                        raise AdapterError(
                            f"{self.name}: invalid JSON response") from exc
                    return self._parse_response(data, resp)

                if resp.status_code in _RETRYABLE_STATUS and attempt < 2:
                    last_error = AdapterError(
                        f"{self.name}: HTTP {resp.status_code}")
                    await asyncio.sleep(2 ** attempt)
                    continue

                raise AdapterError(
                    f"{self.name}: HTTP {resp.status_code}: "
                    f"{resp.text[:500]}")

            raise last_error if last_error else AdapterError(
                f"{self.name}: request failed")
        finally:
            if own_client and client is not None:
                await client.aclose()

    # -- helpers ------------------------------------------------------
    def _parse_response(self, data: dict, resp: httpx.Response) -> Reply:
        choices = data.get("choices") or []
        text = ""
        if choices:
            text = (choices[0].get("message") or {}).get("content") or ""
        raw_usage = data.get("usage") or {}
        usage = {
            "tokens_in": int(raw_usage.get("prompt_tokens", 0)),
            "tokens_out": int(raw_usage.get("completion_tokens", 0)),
            "cost_usd": float(raw_usage.get("cost_usd", 0.0)),
        }
        return Reply(text=text, usage=usage, provider=self.name,
                     family=self.family, raw=resp.text)


def load_from_config(config_path: str | os.PathLike,
                     env: dict | None = None) -> dict[str, Adapter]:
    """Build adapters from ``config/providers.yaml`` + environment.

    Two YAML shapes are supported (the file is shared with other
    MUFAKAT modules, so both must keep working):

    A) contract shape::

        providers:
          - name: deepseek
            family: deepseek
            type: openai_compat
            base_url: https://api.deepseek.com/v1
            api_key_env: DEEPSEEK_API_KEY
            model: deepseek-chat

    B) registry shape::

        adapters:
          deepseek:
            kind: api
            base_url: https://api.deepseek.com/v1
            model: deepseek-chat
            env_key: DEEPSEEK_API_KEY
        cli:
          codex: {kind: cli, command: codex}

    ``env`` defaults to ``os.environ``.  Entries without a resolvable
    API key are skipped (never logged).
    """
    env_map: dict = dict(os.environ) if env is None else dict(env)
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"providers config not found: {config_path}")
    with path.open() as fh:
        cfg: dict = yaml.safe_load(fh) or {}

    adapters: dict[str, Adapter] = {}

    # Shape A: providers list.
    for entry in cfg.get("providers", []) or []:
        if entry.get("type") != "openai_compat":
            continue
        name = entry.get("name")
        api_key = env_map.get(entry.get("api_key_env", ""), "") or ""
        if not name or not api_key:
            continue
        adapters[name] = OpenAICompatAdapter(
            name=name,
            family=entry.get("family", name),
            base_url=entry.get("base_url", ""),
            api_key=api_key,
            model=entry.get("model", ""),
        )

    # Shape B: adapters dict (api entries) + cli section.
    for name, entry in (cfg.get("adapters") or {}).items():
        if not isinstance(entry, dict) or entry.get("kind") != "api":
            continue
        api_key = env_map.get(entry.get("env_key", ""), "") or ""
        if not api_key:
            continue
        adapters.setdefault(name, OpenAICompatAdapter(
            name=name,
            family=entry.get("family", name),
            base_url=entry.get("base_url", ""),
            api_key=api_key,
            model=entry.get("model", ""),
        ))

    from .cli_antigravity import AntigravityAdapter
    from .cli_claude import ClaudeAdapter
    from .cli_codex import CodexAdapter
    from .cli_copilot import CopilotAdapter
    from .cli_opencode import OpenCodeAdapter

    _cli_classes = {
        "codex": CodexAdapter,
        "copilot": CopilotAdapter,
        "antigravity": AntigravityAdapter,
        "claude": ClaudeAdapter,
        "opencode": OpenCodeAdapter,
    }
    for name, entry in (cfg.get("cli") or {}).items():
        cls = _cli_classes.get(name)
        if cls is None:
            continue
        adapters.setdefault(name, cls(name=name, family=name))  # type: ignore[abstract]

    return adapters
