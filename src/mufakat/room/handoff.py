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
import os
import tempfile
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
    # NOTE: "next_round" sengaja TIDAK ada di sini. Dulu transisi
    # next_round/next_round_from_revision bisa dipanggil langsung lewat
    # transition() dan hanya memindah state ke READY_TO_SEND tanpa
    # menaikkan round_no, tanpa membersihkan prompt, dan tanpa reset
    # repair — state dan ronde jadi tidak sinkron. Ronde baru HANYA
    # lewat Room.next_round() yang melakukan semua efek samping itu.
}

MAX_HANDOFF_ROUNDS = 3

# Fase yang diharapkan pada tiap state menunggu impor.
_EXPECTED_PHASE = {
    "WAITING_FOR_IMPORTED_RESPONSE": "proposal",
    "WAITING_FOR_REBUTTAL_IMPORT": "rebuttal",
}


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
        if not isinstance(room_id, str) or not room_id.strip():
            raise RoomError("room_id tidak boleh kosong.")
        if not isinstance(idea, str) or not idea.strip():
            raise RoomError("idea tidak boleh kosong.")
        if providers is None:
            provider_ids = ["chatgpt", "claude", "gemini"]
        else:
            # Dulu `providers or [...]`: list kosong diam-diam diganti
            # 3 provider default. List kosong kini ditolak eksplisit.
            if not providers:
                raise RoomError("providers tidak boleh kosong.")
            provider_ids = list(providers)
        self.room_id = room_id
        self.idea = idea
        self.providers = provider_ids
        for provider_id in self.providers:
            get_provider(provider_id)  # validasi id dikenal
        self.state = "DRAFT"
        self.round_no = 1
        self.prompts: dict[str, dict[str, str]] = {}  # provider -> {template, text}
        self.responses: list[dict[str, Any]] = []
        self.history: list[str] = []
        self.room_dir = Path(room_dir) if room_dir else None
        self.pacing = pacing_ledger or pacing_mod.PacingLedger()
        # Repair format: _repair_attempts[kunci] = jumlah impor rusak
        # untuk provider:ronde itu; _repair_prompt_issued = prompt
        # perbaikan sudah diterbitkan 1x atau belum. Dulu keduanya
        # dicampur dalam satu flag yang diset saat impor rusak — akibatnya
        # format_repair_prompt() selalu menolak tepat setelah impor
        # rusak, jadi alur repair tidak pernah bisa jalan.
        self._repair_attempts: dict[str, int] = {}
        self._repair_prompt_issued: dict[str, bool] = {}

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
        bukan saat menyusun. Bila ada satu saja yang diblokir, TIDAK ADA
        prompt yang disimpan (atomik) — dulu prompt yang lolos sempat
        masuk antrean sebelum error dilempar.
        """
        built: dict[str, str] = {}
        new_prompts: dict[str, dict[str, str]] = {}
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
            new_prompts[provider_id] = {"template": template, "text": text}
        if blocked:
            raise RoomError(f"Prompt diblokir secret scanner: {blocked}")
        self.prompts = new_prompts
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
        recorded = self.pacing.record(provider_id)
        if not recorded.allowed:
            raise RoomError(f"Pacing: {recorded.reason}")
        if self.state == "READY_TO_SEND":
            self.transition("user_copies_prompt")
        self.save()
        return text

    def mark_submitted(self, provider_id: str) -> None:
        """Pengguna menyatakan sudah mengirim prompt di tab resmi provider."""
        get_provider(provider_id)
        if provider_id not in self.providers:
            raise RoomError(f"Provider {provider_id!r} bukan anggota room ini.")
        if self.state == "WAITING_FOR_USER_SUBMISSION":
            self.transition("user_submits")
        elif self.state in ("WAITING_FOR_IMPORTED_RESPONSE", "RESPONSE_IMPORTED"):
            # Sudah ditandai terkirim (oleh provider lain, atau panggilan
            # ulang yang idempotent): tidak ada transisi, bukan error.
            # (Audit Putaran 2: pemanggilan kedua sempat melempar error
            # dan memecahkan alur UI yang memanggil per provider.)
            return
        else:
            raise RoomError(
                f"Tidak bisa menandai terkirim dari state {self.state!r}."
            )

    # -- import jawaban --------------------------------------------------
    def import_response(self, provider_id: str, text: str,
                        phase: str = "proposal") -> dict[str, Any]:
        """Impor jawaban yang disalin pengguna dari tab resmi provider.

        Jawaban diberi label ``"user imported"`` + provenance lengkap.
        Isi jawaban TIDAK diubah; raw text dan hasil parse disimpan
        terpisah. Bila tidak ada blok JSON, respons tetap disimpan dengan
        status ``unparsed`` agar pengguna bisa mengisi manual.

        Validasi: provider harus anggota room, ``phase`` harus dikenal,
        dan pada state menunggu impor fase harus cocok (``proposal`` saat
        menunggu jawaban, ``rebuttal`` saat menunggu rebuttal) — dulu
        fase salah tetap disimpan ke memori lalu transisi gagal, sehingga
        memori dan disk tidak sinkron. Impor ulang provider yang sama
        (ronde + fase sama) MENGGANTI record lama, bukan menumpuk —
        dulu impor ganda menggandakan suara di konsensus.
        """
        provider = get_provider(provider_id)
        if provider_id not in self.providers:
            raise RoomError(f"Provider {provider_id!r} bukan anggota room ini.")
        if self.state == "APPROVED":
            raise RoomError("Room sudah APPROVED (terminal): tidak bisa impor lagi.")
        if phase not in parser_mod.ALLOWED_PHASES:
            raise RoomError(f"Phase tidak dikenal: {phase!r}.")
        expected = _EXPECTED_PHASE.get(self.state)
        if expected is not None and phase != expected:
            raise RoomError(
                f"Phase {phase!r} tidak cocok untuk state {self.state!r} "
                f"(harus {expected!r})."
            )
        if not isinstance(text, str) or not text.strip():
            raise RoomError("Jawaban impor kosong.")
        key = f"{provider_id}:{self.round_no}"
        repair_attempted = self._repair_attempts.get(key, 0) >= 1
        parsed = parser_mod.parse_reply(text, repair_attempted=repair_attempted)
        if parsed.status == "repair_needed":
            self._repair_attempts[key] = self._repair_attempts.get(key, 0) + 1
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
        # Dedup: ganti record lama provider+ronde+fase yang sama.
        replaced = False
        for idx, existing in enumerate(self.responses):
            if (
                existing.get("provider") == provider_id
                and existing.get("round") == self.round_no
                and existing.get("phase") == phase
            ):
                self.responses[idx] = record
                replaced = True
                break
        if not replaced:
            self.responses.append(record)
        if self.state == "WAITING_FOR_IMPORTED_RESPONSE":
            self.transition("response_imported")
        elif self.state == "WAITING_FOR_REBUTTAL_IMPORT":
            self.transition("rebuttal_imported")
        self.save()
        return record

    def format_repair_prompt(self, provider_id: str) -> str:
        """Prompt perbaikan format (maks 1x per provider per ronde).

        Hanya bisa dipakai SETELAH ada impor rusak untuk provider/ronde
        itu, dan hanya sekali. Dulu flag repair diset oleh impor rusak
        itu sendiri, sehingga pemanggilan ini selalu menolak tepat saat
        dibutuhkan.
        """
        if provider_id not in self.providers:
            raise RoomError(f"Provider {provider_id!r} bukan anggota room ini.")
        key = f"{provider_id}:{self.round_no}"
        if self._repair_attempts.get(key, 0) == 0:
            raise RoomError(
                "Belum ada jawaban rusak untuk diperbaiki pada ronde ini."
            )
        if self._repair_prompt_issued.get(key):
            raise RoomError("Prompt perbaikan format sudah dipakai 1x untuk ronde ini.")
        last = self._last_response(provider_id)
        # Jawaban terakhir harus masih rusak: bila impor bagus sudah
        # menggantikannya, prompt repair menyesatkan (error default).
        if last is None or last.get("parse_status") not in ("repair_needed", "unparsed"):
            raise RoomError(
                "Jawaban terakhir provider ini sudah valid; tidak ada yang diperbaiki."
            )
        self._repair_prompt_issued[key] = True
        error = last.get("parse_error", "format JSON tidak valid")
        self.save()
        return parser_mod.format_repair_prompt(error)

    # -- ronde & konsensus ------------------------------------------------
    def next_round(self) -> int:
        """Mulai ronde berikutnya (maks 3); reset antrean prompt."""
        if self.round_no >= MAX_HANDOFF_ROUNDS:
            raise RoomError(f"Batas ronde tercapai ({MAX_HANDOFF_ROUNDS}). Minta keputusan juri.")
        if self.state not in ("RESPONSE_IMPORTED", "REVISION_READY"):
            raise RoomError(f"Tidak bisa mulai ronde baru dari state {self.state!r}.")
        # Semua efek samping dilakukan sekaligus lalu disimpan sekali
        # (dulu transition() dulu baru round_no dinaikkan — save di
        # tengah jalan sempat menulis state baru dengan ronde lama).
        self.state = "READY_TO_SEND"
        self.history.append(f"next_round -> READY_TO_SEND (ronde {self.round_no + 1})")
        self.round_no += 1
        self.prompts = {}
        self._repair_attempts = {}
        self._repair_prompt_issued = {}
        self.save()
        return self.round_no

    def consensus(self) -> dict | None:
        """Hitung konsensus Borda dari vote yang sudah diimpor ronde ini.

        Reuse :mod:`mufakat.consensus.voting` — tidak ada logika voting
        ganda. ``None`` bila belum ada vote yang bisa dihitung.
        Hanya vote fase ``proposal`` ronde ini yang dihitung, satu vote
        per provider (yang pertama), dan hanya ``decision`` yang valid —
        dulu vote rebuttal ikut terhitung ganda bersama vote proposal.
        """
        from mufakat.consensus.voting import VALID_DECISIONS, decide

        votes, critiques = [], []
        seen_providers: set[str] = set()
        for record in self._round_responses(self.round_no, phase="proposal"):
            provider_id = record.get("provider")
            if not isinstance(provider_id, str) or provider_id in seen_providers:
                continue
            parsed = record.get("parsed") or {}
            if not isinstance(parsed, dict):
                continue
            vote = parsed.get("vote")
            if isinstance(vote, dict) and vote.get("decision") in VALID_DECISIONS:
                seen_providers.add(provider_id)
                votes.append({**vote, "agent_id": provider_id})
            parsed_critiques = parsed.get("critiques")
            if isinstance(parsed_critiques, list):
                for crit in parsed_critiques:
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
            "repair_attempts": dict(self._repair_attempts),
            "repair_prompt_issued": dict(self._repair_prompt_issued),
        }

    def save(self) -> None:
        if self.room_dir is None:
            return
        self.room_dir.mkdir(parents=True, exist_ok=True)
        # Tulis atomik (tmp + replace) agar crash di tengah tulis tidak
        # meninggalkan room.json setengah jadi.
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.room_dir), prefix="room.json.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_name, self.room_dir / "room.json")
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        with open(self.room_dir / "transcript.jsonl", "w", encoding="utf-8") as fh:
            for record in self.responses:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, room_dir: str | Path) -> "Room":
        room_dir = Path(room_dir)
        try:
            raw = (room_dir / "room.json").read_text(encoding="utf-8")
        except OSError as exc:
            raise RoomError(f"Tidak bisa membaca room.json: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RoomError(f"room.json rusak (bukan JSON): {exc}") from exc
        if not isinstance(data, dict):
            raise RoomError("room.json rusak: isi harus object JSON.")
        for key in ("room_id", "idea", "providers", "state", "round_no"):
            if key not in data:
                raise RoomError(f"room.json rusak: kunci {key!r} hilang.")
        if not isinstance(data["room_id"], str) or not data["room_id"].strip():
            raise RoomError("room.json rusak: room_id tidak valid.")
        if not isinstance(data["idea"], str):
            raise RoomError("room.json rusak: idea tidak valid.")
        if not isinstance(data["providers"], list) or not all(
            isinstance(p, str) for p in data["providers"]
        ):
            raise RoomError("room.json rusak: providers tidak valid.")
        if data["state"] not in HANDOFF_STATES:
            raise RoomError(f"room.json rusak: state tidak dikenal: {data['state']!r}.")
        round_no = data["round_no"]
        if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no < 1:
            raise RoomError("room.json rusak: round_no tidak valid.")
        if not isinstance(data.get("prompts", {}), dict):
            raise RoomError("room.json rusak: prompts tidak valid.")
        prompts = data.get("prompts", {})
        if any(
            not isinstance(v, dict) or not isinstance(v.get("text"), str)
            for v in prompts.values()
        ):
            raise RoomError("room.json rusak: isi prompts tidak valid.")
        if not isinstance(data.get("responses", []), list):
            raise RoomError("room.json rusak: responses tidak valid.")
        if any(not isinstance(r, dict) for r in data.get("responses", [])):
            raise RoomError("room.json rusak: isi responses tidak valid.")
        room = cls(
            room_id=data["room_id"], idea=data["idea"], providers=data["providers"],
            room_dir=room_dir,
        )
        room.state = data["state"]
        room.round_no = round_no
        room.prompts = data.get("prompts", {})
        room.responses = data.get("responses", [])
        room.history = data.get("history", []) if isinstance(data.get("history"), list) else []
        attempts = data.get("repair_attempts", {})
        if isinstance(attempts, dict):
            room._repair_attempts = {
                str(k): int(v) for k, v in attempts.items()
                if isinstance(v, int) and not isinstance(v, bool)
            }
        issued = data.get("repair_prompt_issued", {})
        if isinstance(issued, dict):
            room._repair_prompt_issued = {
                str(k): bool(v) for k, v in issued.items()
            }
        # Pulihkan pacing dari usage.json bila ada — dulu load() selalu
        # membuat ledger baru sehingga batas harian/jeda bisa dilewati
        # hanya dengan memuat ulang room.
        for candidate in (room_dir / "usage.json", room_dir.parent / "usage.json"):
            if candidate.is_file():
                room.pacing = pacing_mod.PacingLedger.load(candidate)
                break
        return room
