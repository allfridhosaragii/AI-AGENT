"""Registri provider MUFAKAT beserta kapabilitasnya (ChatGPT §2D).

Setiap provider didaftarkan dengan daftar kapabilitas yang didukung,
mis. ``text_generation``, ``tool_calling``, ``mcp_client``, ``a2a``,
dan ``oauth_supported``. Registri ini dipakai router untuk memilih
provider yang cocok dengan kebutuhan tugas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ProviderCapability", "ProviderRegistry", "default_registry"]

# Kapabilitas yang dikenal (ChatGPT §2D).
KNOWN_CAPABILITIES: tuple[str, ...] = (
    "text_generation",
    "streaming",
    "tool_calling",
    "structured_output",
    "vision",
    "code_execution",
    "repository_access",
    "mcp_client",
    "mcp_server",
    "a2a",
    "long_context",
    "oauth_supported",
)


@dataclass
class ProviderCapability:
    """Deskripsi satu provider beserta kapabilitasnya."""

    name: str
    capabilities: list[str] = field(default_factory=list)

    def supports(self, capability: str) -> bool:
        """Kembalikan ``True`` bila provider mendukung ``capability``."""
        return capability in self.capabilities


def _provider(name: str, *capabilities: str) -> ProviderCapability:
    """Bangun :class:`ProviderCapability` dengan validasi nama kapabilitas."""
    unknown = [c for c in capabilities if c not in KNOWN_CAPABILITIES]
    if unknown:
        raise ValueError(f"Kapabilitas tidak dikenal untuk {name}: {unknown}")
    return ProviderCapability(name=name, capabilities=list(capabilities))


class ProviderRegistry:
    """Registri provider yang bisa didaftar, dicari, dan difilter."""

    def __init__(self, providers: list[ProviderCapability] | None = None) -> None:
        self._providers: dict[str, ProviderCapability] = {}
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: ProviderCapability) -> None:
        """Daftarkan (atau timpa) satu provider berdasarkan namanya."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> ProviderCapability | None:
        """Kembalikan provider berdasarkan nama, atau ``None`` bila belum ada."""
        return self._providers.get(name)

    def supports(self, name: str, capability: str) -> bool:
        """Kembalikan ``True`` bila provider ``name`` mendukung ``capability``."""
        provider = self.get(name)
        return provider.supports(capability) if provider is not None else False

    def list_all(self) -> list[ProviderCapability]:
        """Kembalikan semua provider yang terdaftar."""
        return list(self._providers.values())


def default_registry() -> ProviderRegistry:
    """Registri bawaan berisi provider API dan CLI yang didukung MUFAKAT."""
    return ProviderRegistry(
        [
            _provider(
                "deepseek",
                "text_generation",
                "streaming",
                "tool_calling",
                "structured_output",
                "long_context",
            ),
            _provider(
                "openrouter_free",
                "text_generation",
                "streaming",
                "structured_output",
                "long_context",
            ),
            _provider(
                "groq",
                "text_generation",
                "streaming",
                "tool_calling",
                "structured_output",
            ),
            _provider(
                "gemini_api",
                "text_generation",
                "streaming",
                "tool_calling",
                "structured_output",
                "vision",
                "long_context",
            ),
            _provider(
                "meta_api",
                "text_generation",
                "streaming",
                "structured_output",
                "long_context",
            ),
            _provider(
                "codex_cli",
                "text_generation",
                "streaming",
                "tool_calling",
                "code_execution",
                "repository_access",
                "mcp_client",
                "oauth_supported",
            ),
            _provider(
                "copilot_cli",
                "text_generation",
                "streaming",
                "tool_calling",
                "code_execution",
                "repository_access",
                "mcp_client",
                "oauth_supported",
            ),
            _provider(
                "antigravity_cli",
                "text_generation",
                "streaming",
                "tool_calling",
                "code_execution",
                "repository_access",
                "mcp_client",
                "mcp_server",
                "oauth_supported",
            ),
            _provider(
                "claude_cli",
                "text_generation",
                "streaming",
                "tool_calling",
                "structured_output",
                "code_execution",
                "repository_access",
                "mcp_client",
                "mcp_server",
                "a2a",
                "long_context",
                "oauth_supported",
            ),
            _provider(
                "opencode",
                "text_generation",
                "streaming",
                "tool_calling",
                "code_execution",
                "repository_access",
                "mcp_client",
                "mcp_server",
                "a2a",
                "oauth_supported",
            ),
        ]
    )
