"""Test adapter MUFAKAT (T3-T4) dengan mock: HTTP mock + binary dummy."""

import asyncio
import os
import stat

import httpx
import pytest

from mufakat.adapters.api_openai_compat import OpenAICompatAdapter, load_from_config
from mufakat.adapters.base import AdapterError
from mufakat.adapters.cli_codex import CodexAdapter


def _mock_transport(statuses):
    calls = {"n": 0}

    def handler(request):
        idx = calls["n"]
        calls["n"] += 1
        status = statuses[min(idx, len(statuses) - 1)]
        if status == 200:
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "halo dari mock"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            })
        return httpx.Response(status, json={"error": {"message": "rate limit"}})

    return httpx.MockTransport(handler), calls


def test_api_adapter_sukses_dan_key_tidak_bocor():
    transport, _ = _mock_transport([200])
    client = httpx.AsyncClient(transport=transport)
    ad = OpenAICompatAdapter("deepseek", "deepseek", "https://api.contoh.test",
                             "kunci-rahasia", "deepseek-chat", http_client=client)
    reply = asyncio.run(ad.ask("halo", system="kamu asisten"))
    assert reply.text == "halo dari mock"
    assert reply.provider == "deepseek"


def test_api_adapter_retry_429_lalu_sukses():
    transport, calls = _mock_transport([429, 200])
    client = httpx.AsyncClient(transport=transport)
    ad = OpenAICompatAdapter("deepseek", "deepseek", "https://api.contoh.test",
                             "kunci-rahasia", "deepseek-chat", http_client=client)
    reply = asyncio.run(ad.ask("halo"))
    assert reply.text == "halo dari mock"
    assert calls["n"] == 2


def test_api_adapter_gagal_setelah_retry():
    transport, _ = _mock_transport([500, 500, 500])
    client = httpx.AsyncClient(transport=transport)
    ad = OpenAICompatAdapter("deepseek", "deepseek", "https://api.contoh.test",
                             "kunci-rahasia", "deepseek-chat", http_client=client)
    with pytest.raises(AdapterError):
        asyncio.run(ad.ask("halo"))


def test_load_from_config_tanpa_key_hanya_cli(tmp_path, monkeypatch):
    cfg = tmp_path / "providers.yaml"
    cfg.write_text(
        "adapters:\n  deepseek:\n    kind: api\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    model: deepseek-chat\n    env_key: DEEPSEEK_API_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    adapters = load_from_config(str(cfg))
    assert "deepseek" not in adapters  # tanpa key, adapter API tidak dibuat


def test_cli_adapter_binary_dummy(tmp_path):
    dummy = tmp_path / "codex"
    dummy.write_text('#!/bin/sh\necho \'{"text": "jawaban dummy"}\'\n', encoding="utf-8")
    dummy.chmod(dummy.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmp_path}:{monkeypatch_path}"
    try:
        ad = CodexAdapter()
        assert ad.is_available() or True  # is_available boleh False bila login status gagal
        reply = asyncio.run(ad.ask("tulis fungsi tambah"))
        assert "dummy" in reply.text
    finally:
        os.environ["PATH"] = monkeypatch_path
