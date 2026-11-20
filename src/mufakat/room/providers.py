"""Provider registry MUFAKAT Room (V3 §2.5, Addendum C & G).

Status per provider ditulis JUJUR — tidak pernah diklaim "connected"
bila yang terjadi hanya manual handoff. Nilai default:

- ``manual_handoff`` — ChatGPT, Claude, Gemini, DeepSeek, Qwen.
  Otomasi prompt submission / response retrieval TIDAK diizinkan
  (``False``); pengguna menyalin prompt dan menempel jawaban sendiri.
- ``needs_policy_review`` — Muse: identitas situs, akun, dan ketentuan
  produk yang tepat belum terverifikasi; tetap manual handoff sampai
  situs dan kebijakannya terverifikasi.

``terms_last_verified_at`` mengikuti snapshot Addendum G V3 (bukan
verifikasi baru di VM ini — lihat catatan di tiap entri). Bila suatu
saat ada connector resmi terverifikasi, ubah entri ini beserta tanggal
dan URL buktinya; jangan ubah status tanpa bukti.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Provider",
    "PROVIDERS",
    "get_provider",
    "list_providers",
    "honest_status_label",
    "MANUAL_HANDOFF_PROVIDERS",
]

# Label status koneksi (V3 Addendum C) — jangan pakai badge "Connected" umum.
STATUS_LABELS = {
    "not_connected": "Not connected",
    "official_site_opened": "Official site opened",
    "ready_for_manual_handoff": "Ready for manual handoff",
    "official_integration_connected": "Official integration connected",
    "manual_handoff_only": "Manual handoff only",
    "disabled_by_policy": "Disabled by policy",
    "needs_policy_review": "Needs policy review",
}


@dataclass(frozen=True)
class Provider:
    """Deklarasi kapabilitas browser satu provider (V3 §2.5)."""

    id: str
    name: str
    family: str
    official_url: str
    integration_status: str  # "manual_handoff" | "needs_policy_review" | ...
    official_connection_supported: bool = False
    delegated_auth_supported: bool = False
    embedded_ui_supported: bool = False
    manual_handoff_supported: bool = True
    automated_prompt_submission_allowed: bool = False
    automated_response_retrieval_allowed: bool = False
    provider_connector_available: bool = False
    subscription_account_eligible: bool | None = None
    revocation_supported: bool = False
    terms_last_verified_at: str | None = None
    evidence_urls: tuple[str, ...] = ()
    policy_note: str = ""


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="chatgpt",
        name="ChatGPT",
        family="openai",
        official_url="https://chatgpt.com/",
        integration_status="manual_handoff",
        terms_last_verified_at="2026-01-01",
        evidence_urls=("https://openai.com/policies/terms-of-use/",),
        policy_note=(
            "Terms of Use efektif 1 Jan 2026 melarang automatic/programmatic "
            "extraction of data or Output serta circumventing rate limits. "
            "Default: manual handoff; jangan buat automatic answer extraction."
        ),
    ),
    Provider(
        id="claude",
        name="Claude",
        family="anthropic",
        official_url="https://claude.ai/",
        integration_status="manual_handoff",
        evidence_urls=(
            "https://assets.claude.com/399b2834d66aef85393d3c0ebe02a68c58dd59a3.pdf",
            "https://code.claude.com/docs/en/legal-and-compliance",
        ),
        policy_note=(
            "Consumer Terms melarang akses automated/non-human via bot/script "
            "kecuali API key atau izin eksplisit; third-party apps dilarang "
            "menawarkan login Claude.ai atau mengintermediasi kredensial langganan. "
            "Manual handoff untuk situs consumer."
        ),
    ),
    Provider(
        id="gemini",
        name="Gemini",
        family="google",
        official_url="https://gemini.google.com/",
        integration_status="manual_handoff",
        evidence_urls=(
            "https://policies.google.com/terms",
            "https://support.google.com/gemini/answer/16821166",
        ),
        policy_note=(
            "Google Terms melarang automated access bila melanggar machine-readable "
            "instructions. Gemini in Chrome adalah fitur Google sendiri, bukan izin "
            "otomatis bagi aplikasi pihak ketiga. Manual handoff sampai izin "
            "eksplisit diverifikasi."
        ),
    ),
    Provider(
        id="deepseek",
        name="DeepSeek",
        family="deepseek",
        official_url="https://chat.deepseek.com/",
        integration_status="manual_handoff",
        terms_last_verified_at="2026-03-27",
        evidence_urls=("https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html",),
        policy_note=(
            "Terms of Use (diperbarui 27 Mar 2026) melarang pencurian data dan "
            "menyebut capture/copying content memakai robots, spiders, atau "
            "automatic setups. Manual handoff default; jangan scraping."
        ),
    ),
    Provider(
        id="qwen",
        name="Qwen",
        family="qwen",
        official_url="https://chat.qwen.ai/",
        integration_status="manual_handoff",
        terms_last_verified_at="2026-05-19",
        evidence_urls=("https://qwen.ai/termsservice",),
        policy_note=(
            "Terms of Service (diperbarui 19 Mei 2026) melarang interaksi, "
            "ekstraksi, atau pengunduhan konten/Output secara otomatis, "
            "termasuk scraping atau agents. Manual handoff default."
        ),
    ),
    Provider(
        id="muse",
        name="Muse",
        family="meta",
        official_url="https://www.meta.ai/",
        integration_status="needs_policy_review",
        subscription_account_eligible=None,
        policy_note=(
            "Identitas situs, akun, dan ketentuan produk Muse/Muse Spark yang "
            "tepat harus dikonfirmasi dari URL yang benar-benar digunakan pengguna. "
            "Jangan samakan model/API dengan website chat tanpa bukti. "
            "Status: needs policy review; manual handoff sampai terverifikasi."
        ),
    ),
)

MANUAL_HANDOFF_PROVIDERS = tuple(p.id for p in PROVIDERS)


def get_provider(provider_id: str) -> Provider:
    """Kembalikan provider berdasarkan id; ``ValueError`` bila tak dikenal."""
    for provider in PROVIDERS:
        if provider.id == provider_id:
            return provider
    raise ValueError(f"Provider tidak dikenal: {provider_id!r}")


def list_providers() -> list[Provider]:
    """Semua provider terdaftar, sesuai urutan registry."""
    return list(PROVIDERS)


def honest_status_label(provider: Provider) -> str:
    """Label status jujur untuk UI (V3 Addendum C).

    Manual handoff default -> "Manual handoff only". Muse ->
    "Needs policy review". TIDAK PERNAH "Connected" untuk manual handoff.
    """
    if provider.integration_status == "needs_policy_review":
        return STATUS_LABELS["needs_policy_review"]
    if provider.integration_status == "manual_handoff":
        return STATUS_LABELS["manual_handoff_only"]
    if provider.integration_status == "official_connected":
        return STATUS_LABELS["official_integration_connected"]
    return STATUS_LABELS["not_connected"]


def provider_summary(provider: Provider) -> dict:
    """Ringkasan registry satu provider untuk UI/audit (tanpa rahasia)."""
    return {
        "id": provider.id,
        "name": provider.name,
        "official_url": provider.official_url,
        "integration_status": provider.integration_status,
        "status_label": honest_status_label(provider),
        "manual_handoff_supported": provider.manual_handoff_supported,
        "automated_prompt_submission_allowed": provider.automated_prompt_submission_allowed,
        "automated_response_retrieval_allowed": provider.automated_response_retrieval_allowed,
        "terms_last_verified_at": provider.terms_last_verified_at,
        "evidence_urls": list(provider.evidence_urls),
    }
