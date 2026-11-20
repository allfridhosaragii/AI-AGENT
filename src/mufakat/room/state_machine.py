"""State machine debat MUFAKAT Room (Claude §2, §T6).

Alur: Ide -> Usulan_R1 -> KritikSilang -> Rapat -> (DebatUlang <= 3 ronde
atau Spesifikasi) -> ApproveSpek -> Coding -> ReviewSilang ->
TerapkanPatch -> Gates -> (Revisi <= 5 / AuditFinal / Eskalasi) ->
ApproveCommit -> Selesai.

Mesin ini murni (tanpa I/O): transisi divalidasi, ronde/iterasi dihitung,
dan eskalasi dipicu saat batas tercapai. State machine manual handoff
V3 Addendum F (DRAFT -> ... -> APPROVED) hidup di
:mod:`mufakat.room.handoff` — keduanya dipakai bersama: handoff mengatur
perpindahan prompt/jawaban dengan pengguna, mesin ini mengatur fase
debat/kode di dalamnya.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "DebateMachine",
    "IllegalTransition",
    "MAX_DEBATE_ROUNDS",
    "MAX_FIX_ITERATIONS",
    "MAX_TOTAL_ITERATIONS",
    "STATES",
    "TRANSITIONS",
]

MAX_DEBATE_ROUNDS = 3
MAX_FIX_ITERATIONS = 5
MAX_TOTAL_ITERATIONS = 12

STATES = (
    "ide",
    "usulan_r1",
    "kritik_silang",
    "rapat",
    "debat_ulang",
    "spesifikasi",
    "approve_spek",
    "coding",
    "review_silang",
    "terapkan_patch",
    "gates",
    "revisi",
    "audit_final",
    "approve_commit",
    "eskalasi",
    "selesai",
)

# event -> (dari_state, ke_state)
TRANSITIONS: dict[str, tuple[str, str]] = {
    "kirim_ide": ("ide", "usulan_r1"),
    "usulan_diterima": ("usulan_r1", "kritik_silang"),
    "kritik_diterima": ("kritik_silang", "rapat"),
    "belum_mufakat": ("rapat", "debat_ulang"),
    "debat_lanjut": ("debat_ulang", "kritik_silang"),
    "mufakat_atau_juri": ("rapat", "spesifikasi"),
    "spek_revisi": ("approve_spek", "spesifikasi"),
    "spek_disetujui": ("approve_spek", "coding"),
    "spek_selesai": ("spesifikasi", "approve_spek"),
    "kode_selesai": ("coding", "review_silang"),
    "review_selesai": ("review_silang", "terapkan_patch"),
    "patch_disetujui": ("terapkan_patch", "gates"),
    "gate_gagal": ("gates", "revisi"),
    "gate_lulus": ("gates", "audit_final"),
    "gate_eskalasi": ("gates", "eskalasi"),
    "revisi_selesai": ("revisi", "review_silang"),
    "audit_bersih": ("audit_final", "approve_commit"),
    "audit_temuan": ("audit_final", "revisi"),
    "commit_disetujui": ("approve_commit", "selesai"),
    "eskalasi_selesai": ("eskalasi", "selesai"),
}


class IllegalTransition(ValueError):
    """Event tidak valid dari state saat ini."""


@dataclass
class DebateMachine:
    """State machine debat -> kode -> audit (murni, tanpa I/O)."""

    state: str = "ide"
    debate_round: int = 0
    fix_iterations: int = 0
    total_iterations: int = 0
    history: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise IllegalTransition(f"State awal tidak dikenal: {self.state!r}")
        if self.debate_round < 0 or self.fix_iterations < 0 or self.total_iterations < 0:
            raise ValueError("Penghitung ronde/iterasi tidak boleh negatif.")

    def transition(self, event: str) -> str:
        """Jalankan ``event``; kembalikan state baru.

        Melempar :class:`IllegalTransition` bila event tidak valid dari
        state saat ini, dan memicu eskalasi otomatis bila batas ronde /
        iterasi tercapai (bukan diam-diam melanjutkan).
        """
        if event not in TRANSITIONS:
            raise IllegalTransition(f"Event tidak dikenal: {event!r}")
        expected_from, target = TRANSITIONS[event]
        if self.state != expected_from:
            raise IllegalTransition(
                f"Event {event!r} tidak valid dari state {self.state!r} "
                f"(harus dari {expected_from!r})."
            )
        # total_iterations menghitung SEMUA transisi (debat + perbaikan):
        # dulu hanya revisi_selesai yang menambahkannya, sehingga batas
        # MAX_TOTAL_ITERATIONS (12) tidak pernah tercapai sebelum
        # MAX_FIX_ITERATIONS (5) — batas total praktis mati.
        self.total_iterations += 1
        if event == "debat_lanjut":
            self.debate_round += 1
            if self.debate_round >= MAX_DEBATE_ROUNDS:
                self.state = "eskalasi"
                self.history.append("eskalasi: batas ronde debat tercapai")
                return self.state
        if event == "revisi_selesai":
            self.fix_iterations += 1
            if (self.fix_iterations >= MAX_FIX_ITERATIONS
                    or self.total_iterations >= MAX_TOTAL_ITERATIONS):
                self.state = "eskalasi"
                self.history.append("eskalasi: batas iterasi perbaikan tercapai")
                return self.state
        if event == "kirim_ide":
            self.debate_round = 1
        self.state = target
        self.history.append(f"{event} -> {target}")
        return self.state

    @property
    def is_terminal(self) -> bool:
        return self.state in ("selesai", "eskalasi")

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "debate_round": self.debate_round,
            "fix_iterations": self.fix_iterations,
            "total_iterations": self.total_iterations,
            "history": list(self.history),
        }
