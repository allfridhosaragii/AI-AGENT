"""Public exports for the adapters package."""

from .api_openai_compat import OpenAICompatAdapter, load_from_config
from .base import Adapter, AdapterError, Reply
from .cli_antigravity import AntigravityAdapter
from .cli_claude import ClaudeAdapter
from .cli_codex import CodexAdapter
from .cli_copilot import CopilotAdapter
from .cli_opencode import OpenCodeAdapter

__all__ = [
    "Adapter",
    "AdapterError",
    "Reply",
    "OpenAICompatAdapter",
    "load_from_config",
    "AntigravityAdapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "CopilotAdapter",
    "OpenCodeAdapter",
]
