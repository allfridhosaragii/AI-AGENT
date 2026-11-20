"""Manual Handoff MUFAKAT Room — MODE DEFAULT (V3 §2.2 Mode B, Addendum F).

Ini mode default dan satu-satunya mode yang aktif di MVP. Alur:

1. Orchestrator menyusun prompt per provider (``build_prompts``).
2. Prompt dipindai secret scanner + diperiksa pacing SEBELUM boleh disalin.
3. Pengguna menekan Copy, menempel ke tab resmi provider, mengirim sendiri.
4. Pengguna menyalin jawaban dan menempelkannya ke ``import_response``.
5. Jawaban disimpan dengan label "user imported" + provenance
   (provider, ronde, waktu impor). TIDAK PERNAH diklaim otomatis.

State machine (V3 Addendum F)::

    DRAFT -> READY_TO_SEND -> WAITING_FOR_USER_SUBMISSION
      -> WAITING_FOR_IMPORTED_RESPONSE -> RESPONSE_IMPORTED
      -> CRITIQUE_READY -> WAITING_FOR_REBUTTAL_IMPORT
      -> REVISION_READY -> FINAL_REVIEW -> APPROVED

State machine TIDAK boleh jalan seolah provider sudah menjawab bila
pengguna belum mengimpor responsnya. Transisi yang menuntut jawaban
menolak bila respons ronde itu belum ada.

Penyimpanan lokal: ``room.json`` + ``transcript.jsonl`` di direktori room
(lihat :mod:`mufakat.room.storage` untuk varian SQLite). Tidak ada server
eksternal / analytics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mufakat.room import pacing as pacing_mod
from mufakat.room import parser as parser_mod
from mufakat.room import prompts as prompts_mod
from mufakat.room import secret_scan as secret_scan_mod
from mufakat.room.providers import get_provider, honest_status_label

__all__ = [
    "Room",
    "RoomError",
    "HANDOFF_STATES",
    "HANDOFF_TRANSITIONS",
    "MAX_HANDOFF_ROUNDS",
]

HANDOFF_STATES = (
    "DRAFT",
    "READY_TO_SEND",
    "WAITING_FOR_USER_SUBMISSION",
    "WAITING_FOR_IMPORTED_RESPONSE",
    "RESPONSE_IMPORTED",
    "CRITIQUE_READY",
    "WAITING_FOR_REBUTTAL_IMPORT",
    "REVISION_READY",
    "FINAL_REVIEW",
    "APPROVED",
)

HANDOFF_TRANSITIONS: dict[str, tuple[str, str]] = {
    "prompts_ready": ("DRAFT", "READY_TO_SEND"),
    "user_copies_prompt": ("READY_TO_SEND", "WAITING_FOR_USER_SUBMISSION"),
    "user_submits": ("WAITING_FOR_USER_SUBMISSION", "WAITING_FOR_IMPORTED_RESPONSE"),
    "response_imported": ("WAITING_FOR_IMPORTED_RESPONSE", "RESPONSE_IMPORTED"),
    "critique_prepared": ("RESPONSE_IMPORTED", "CRITIQUE_READY"),
    "critique_sent": ("CRITIQUE_READY", "WAITING_FOR_REBUTTAL_IMPORT"),
    "rebuttal_imported": ("WAITING_FOR_REBUTTAL_IMPORT", "REVISION_READY"),
    "revision_prepared": ("REVISION_READY", "FINAL_REVIEW"),
    "request_changes": ("FINAL_REVIEW", "CRITIQUE_READY"),
    "approve": ("FINAL_REVIEW", "APPROVED"),
    # Jalur pintas yang jujur: bila ronde sudah selesai tanpa kritik
    # lanjutan, RESPONSE_IMPORTED boleh langsung ke FINAL_REVIEW.
    "finalize": ("RESPONSE_IMPORTED", "FINAL_REVIEW"),
    # Pengguna boleh kembali menyiapkan prompt baru dari state mana pun
    # yang masih butuh kiriman (ronde berikutnya).
    "next_round": ("RESPONSE_IMPORTED", "READY_TO_SEND"),
    "next_round_from_revision": ("REVISION_READY", "READY_TO_SEND"),
}

MAX_HANDOFF_ROUNDS = 3


class RoomError(ValueError):
    """Error alur Room: transisi ilegal, secret terdeteksi, pacing, dsb."""


class Room:
    """Satu AI Room: satu ide, beberapa provider, ronde manual handoff."""

    def __init__(
        self,
        room_id: str,
        idea: str,
        providers: list[str] | None = None,
        room_dir: str | Path | None = None,
        pacing_ledger: pacing_mod.PacingLedger | None = None,
    ) -> None:
        self.room_id = room_id
        self.idea = idea
        self.providers = list(providers or ["chatgpt", "claude", "gemini"])
        for provider_id in self.providers:
            get_provider(provider_id)  # validasi id dikenal
        self.state = "DRAFT"
        self.round_no = 1
        self.prompts: dict[str, dict[str, str]] = {}  # provider -> {template, text}
        self.responses: list[dict[str, Any]] = []
        self.history: list[str] = []
        self.room_dir = Path(room_dir) if room_dir else None
        self.pacing = pacing_ledger or pacing_mod.PacingLedger()
        self._repair_used: dict[str, bool] = {}

    # -- state machine ---------------------------------------------------
    def transition(self, event: str) -> str:
        if event not in HANDOFF_TRANSITIONS:
            raise RoomError(f"Event handoff tidak dikenal: {event!r}")
        expected_from, target = HANDOFF_TRANSITIONS[event]
        if self.state != expected_from:
            raise RoomError(
                f"Event {event!r} tidak valid dari state {self.state!r} "
                f"(harus dari {expected_from!r})."
            )
        if event == "response_imported" and not self._round_responses(self.round_no):
            raise RoomError(
                "Tidak bisa pindah ke RESPONSE_IMPORTED: belum ada respons "
                f"yang diimpor untuk ronde {self.round_no}."
            )
        has_rebuttal = bool(self._round_responses(self.round_no, phase="rebuttal"))
        if event == "rebuttal_imported" and not has_rebuttal:
            raise RoomError(
                "Tidak bisa pindah ke REVISION_READY: belum ada rebuttal "
                f"yang diimpor untuk ronde {self.round_no}."
            )
        self.state = target
        self.history.append(f"{event} -> {target}")
        self.save()
        return self.state

    # -- prompt queue ----------------------------------------------------
    def build_prompts(self, template: str = "proposal", context: str = "",
                      role: str = "debater") -> dict[str, str]:
        """Susun prompt per provider untuk ronde saat ini.

        Prompt dipindai secret scanner; bila ada temuan, prompt provider
        itu DIBLOKIR (tidak masuk antrean) dan error dirinci. Pacing
        diperiksa saat ``copy_prompt`` (saat pengguna benar-benar menyalin),
        bukan saat menyusun.
        """
        built: dict[str, str] = {}
        blocked: dict[str, list[dict[str, str]]] = {}
        for provider_id in self.providers:
            text = prompts_mod.render_prompt(
                template, idea=self.idea, context=context, role=role,
                round_no=self.round_no,
            )
            findings = secret_scan_mod.scan_text(text)
            if findings:
                blocked[provider_id] = [f.as_dict() for f in findings]
                continue
            built[provider_id] = text
            self.prompts[provider_id] = {"template": template, "text": text}
        if blocked:
            raise RoomError(f"Prompt diblokir secret scanner: {blocked}")
        if self.state == "DRAFT":
            self.transition("prompts_ready")
        self.save()
        return built

    def copy_prompt(self, provider_id: str) -> str:
        """Kembalikan teks prompt untuk disalin pengguna (aksi sadar).

        Dijaga pacing (min 20 detik, maks 40/hari per situs) dan secret
        scan. Menyalin di sini TIDAK mengirim apa pun ke situs AI —
        pengguna yang menempel + menekan Kirim di tab resmi provider.
        """
        if provider_id not in self.prompts:
            raise RoomError(f"Belum ada prompt untuk {provider_id} di ronde ini.")
        get_provider(provider_id)  # validasi id dikenal
        decision = self.pacing.check(provider_id)
        if not decision.allowed:
            raise RoomError(f"Pacing: {decision.reason}")
        text = self.prompts[provider_id]["text"]
        findings = secret_scan_mod.scan_text(text)
        if findings:
            raise RoomError(
                f"Prompt diblokir secret scanner: {[f.as_dict() for f in findings]}"
            )
        self.pacing.record(provider_id)
        if self.state == "READY_TO_SEND":
            self.transition("user_copies_prompt")
        self.save()
        return text

    def mark_submitted(self, provider_id: str) -> None:
        """Pengguna menyatakan sudah mengirim prompt di tab resmi provider."""
        get_provider(provider_id)
        if self.state == "WAITING_FOR_USER_SUBMISSION":
            self.transition("user_submits")

    # -- import jawaban --------------------------------------------------
    def import_response(self, provider_id: str, text: str,
                        phase: str = "proposal") -> dict[str, Any]:
        """Impor jawaban yang disalin pengguna dari tab resmi provider.

        Jawaban diberi label ``"user imported"`` + provenance lengkap.
        Isi jawaban TIDAK diubah; raw text dan hasil parse disimpan
        terpisah. Bila tidak ada blok JSON, respons tetap disimpan dengan
        status ``unparsed`` agar pengguna bisa mengisi manual.
        """
        provider = get_provider(provider_id)
        if not text or not text.strip():
            raise RoomError("Jawaban impor kosong.")
        repair_used = self._repair_used.get(f"{provider_id}:{self.round_no}", False)
        parsed = parser_mod.parse_reply(text, repair_attempted=repair_used)
        if parsed.status == "repair_needed":
            self._repair_used[f"{provider_id}:{self.round_no}"] = True
        record = {
            "provider": provider_id,
            "provider_name": provider.name,
            "provider_status_label": honest_status_label(provider),
            "round": self.round_no,
            "phase": phase,
            "source": "user imported",
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "raw_text": text,
            "parse_status": parsed.status,
            "parsed": parsed.payload,
            "parse_error": parsed.error,
        }
        self.responses.append(record)
        if self.state == "WAITING_FOR_IMPORTED_RESPONSE":
            self.transition("response_imported")
        elif self.state == "WAITING_FOR_REBUTTAL_IMPORT":
            self.transition("rebuttal_imported")
        self.save()
        return record

    def format_repair_prompt(self, provider_id: str) -> str:
        """Prompt perbaikan format (maks 1x per provider per ronde)."""
        key = f"{provider_id}:{self.round_no}"
        if self._repair_used.get(key):
            raise RoomError("Prompt perbaikan format sudah dipakai 1x untuk ronde ini.")
        last = self._last_response(provider_id)
        error = (last or {}).get("parse_error", "format JSON tidak valid")
        return parser_mod.format_repair_prompt(error)

    # -- ronde & konsensus ------------------------------------------------
    def next_round(self) -> int:
        """Mulai ronde berikutnya (maks 3); reset antrean prompt."""
        if self.round_no >= MAX_HANDOFF_ROUNDS:
            raise RoomError(f"Batas ronde tercapai ({MAX_HANDOFF_ROUNDS}). Minta keputusan juri.")
        if self.state == "RESPONSE_IMPORTED":
            self.transition("next_round")
        elif self.state == "REVISION_READY":
            self.transition("next_round_from_revision")
        else:
            raise RoomError(f"Tidak bisa mulai ronde baru dari state {self.state!r}.")
        self.round_no += 1
        self.prompts = {}
        self._repair_used = {}
        self.save()
        return self.round_no

    def consensus(self) -> dict | None:
        """Hitung konsensus Borda dari vote yang sudah diimpor ronde ini.

        Reuse :mod:`mufakat.consensus.voting` — tidak ada logika voting
        ganda. ``None`` bila belum ada vote yang bisa dihitung.
        """
        from mufakat.consensus.voting import decide

        votes, critiques = [], []
        for record in self._round_responses(self.round_no):
            parsed = record.get("parsed") or {}
            vote = parsed.get("vote")
            if isinstance(vote, dict) and vote.get("decision"):
                votes.append(vote)
            for crit in parsed.get("critiques") or []:
                if isinstance(crit, dict):
                    critiques.append(crit)
        if not votes:
            return None
        return decide(votes, critiques)

    # -- helpers ----------------------------------------------------------
    def _round_responses(self, round_no: int, phase: str | None = None) -> list[dict]:
        return [
            r for r in self.responses
            if r["round"] == round_no and (phase is None or r.get("phase") == phase)
        ]

    def _last_response(self, provider_id: str) -> dict | None:
        for record in reversed(self.responses):
            if record["provider"] == provider_id and record["round"] == self.round_no:
                return record
        return None

    def provider_statuses(self) -> list[dict]:
        from mufakat.room.providers import provider_summary

        return [provider_summary(get_provider(p)) for p in self.providers]

    # -- persistensi ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "idea": self.idea,
            "providers": list(self.providers),
            "state": self.state,
            "round_no": self.round_no,
            "prompts": self.prompts,
            "responses": self.responses,
            "history": list(self.history),
            "mode": "manual_handoff",
        }

    def save(self) -> None:
        if self.room_dir is None:
            return
        self.room_dir.mkdir(parents=True, exist_ok=True)
        (self.room_dir / "room.json").write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with open(self.room_dir / "transcript.jsonl", "w", encoding="utf-8") as fh:
            for record in self.responses:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, room_dir: str | Path) -> "Room":
        room_dir = Path(room_dir)
        data = json.loads((room_dir / "room.json").read_text(encoding="utf-8"))
        room = cls(
            room_id=data["room_id"], idea=data["idea"], providers=data["providers"],
            room_dir=room_dir,
        )
        room.state = data["state"]
        room.round_no = data["round_no"]
        room.prompts = data.get("prompts", {})
        room.responses = data.get("responses", [])
        room.history = data.get("history", [])
        return room
