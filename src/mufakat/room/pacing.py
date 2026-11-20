"""Pacing / rem kecepatan MUFAKAT Room (Claude §0.1, §T8).

- Jeda minimum 20 detik antar-prompt ke situs yang sama.
- Batas harian per situs default 40 prompt (bisa diubah).
- Bila batas tercapai, ronde DITUNDA (bukan diakali).

Ledger disimpan sebagai JSON lokal (``usage.json``) — tidak ada server
eksternal. Jam bisa di-inject (``clock``) agar mudah diuji.

Hari dihitung dari jam UTC yang sama dengan ``clock`` (bukan
``date.today()`` lokal): dulu batas harian memakai tanggal lokal host
sementara ``clock`` yang di-inject diabaikan, sehingga hari tidak
pernah berganti dalam test dan batas harian bisa salah hitung bila
zona waktu host berbeda dari UTC.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

__all__ = ["PacingLedger", "PacingDecision"]

DEFAULT_MIN_INTERVAL_SECONDS = 20
DEFAULT_DAILY_LIMIT = 40


@dataclass(frozen=True)
class PacingDecision:
    """Hasil pemeriksaan pacing untuk satu situs."""

    allowed: bool
    reason: str
    wait_seconds: float = 0.0
    used_today: int = 0
    daily_limit: int = DEFAULT_DAILY_LIMIT


@dataclass
class PacingLedger:
    """Catatan pemakaian per situs: waktu kirim terakhir + hitungan harian."""

    path: str | Path | None = None
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    daily_limit: int = DEFAULT_DAILY_LIMIT
    clock: object = None  # callable -> float (time.time), untuk test
    _last_sent: dict[str, float] = field(default_factory=dict, repr=False)
    _daily: dict[str, dict[str, int]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds tidak boleh negatif.")
        if self.daily_limit < 0:
            raise ValueError("daily_limit tidak boleh negatif.")

    def _now(self) -> float:
        if self.clock is not None:
            return float(self.clock())  # type: ignore[operator]
        return time.time()

    def _today(self, now: float | None = None) -> str:
        """Tanggal UTC dari ``now`` (jam yang sama dengan clock)."""
        ts = self._now() if now is None else now
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()

    def _prune_old_days(self, today: str) -> None:
        """Buang hitungan hari lama agar ``_daily``/``usage.json`` tak tumbuh tanpa batas.

        Hanya hari ini dan kemarin yang dipertahankan (kemarin untuk
        jaga-jaga bila jam mundur sedikit); sisanya tidak relevan lagi
        untuk batas harian.
        """
        try:
            today_date = datetime.fromisoformat(today).date()
        except ValueError:
            return
        keep = {(today_date - timedelta(days=1)).isoformat(), today}
        for site in list(self._daily):
            self._daily[site] = {
                day: count for day, count in self._daily[site].items() if day in keep
            }
            if not self._daily[site]:
                del self._daily[site]

    # -- pemeriksaan -----------------------------------------------------
    def check(self, site: str) -> PacingDecision:
        """Periksa apakah prompt boleh disalin/dikirim ke ``site`` sekarang."""
        now = self._now()
        today = self._today(now)
        used = self._daily.get(site, {}).get(today, 0)
        if used >= self.daily_limit:
            return PacingDecision(
                allowed=False,
                reason=f"Batas harian tercapai ({used}/{self.daily_limit} prompt ke {site}). "
                "Ronde ditunda sampai besok.",
                used_today=used,
                daily_limit=self.daily_limit,
            )
        last = self._last_sent.get(site)
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_interval_seconds:
                return PacingDecision(
                    allowed=False,
                    reason=f"Jeda minimum belum terpenuhi untuk {site}.",
                    wait_seconds=self.min_interval_seconds - elapsed,
                    used_today=used,
                    daily_limit=self.daily_limit,
                )
        return PacingDecision(
            allowed=True, reason="OK", used_today=used, daily_limit=self.daily_limit
        )

    def record(self, site: str) -> PacingDecision:
        """Catat satu prompt ke ``site``. Harus didahului :meth:`check`.

        Satu snapshot ``now`` dipakai untuk check + pencatatan agar
        jam yang bergerak di tengah jalan tidak membuat hitungan
        dan tanggal tidak konsisten.
        """
        now = self._now()
        today = self._today(now)
        used = self._daily.get(site, {}).get(today, 0)
        if used >= self.daily_limit:
            return PacingDecision(
                allowed=False,
                reason=f"Batas harian tercapai ({used}/{self.daily_limit} prompt ke {site}). "
                "Ronde ditunda sampai besok.",
                used_today=used,
                daily_limit=self.daily_limit,
            )
        last = self._last_sent.get(site)
        if last is not None and now - last < self.min_interval_seconds:
            return PacingDecision(
                allowed=False,
                reason=f"Jeda minimum belum terpenuhi untuk {site}.",
                wait_seconds=self.min_interval_seconds - (now - last),
                used_today=used,
                daily_limit=self.daily_limit,
            )
        self._last_sent[site] = now
        self._daily.setdefault(site, {})[today] = used + 1
        self._prune_old_days(today)
        self.save()
        return PacingDecision(
            allowed=True,
            reason="OK",
            used_today=self._daily[site][today],
            daily_limit=self.daily_limit,
        )

    def used_today(self, site: str) -> int:
        return self._daily.get(site, {}).get(self._today(), 0)

    # -- persistensi -----------------------------------------------------
    def save(self) -> None:
        if self.path is None:
            return
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"last_sent": self._last_sent, "daily": self._daily},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(
        cls,
        path: str | Path,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
    ) -> "PacingLedger":
        ledger = cls(path=path, min_interval_seconds=min_interval_seconds, daily_limit=daily_limit)
        file = Path(path)
        if file.is_file():
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return ledger
                last_sent = data.get("last_sent") or {}
                daily = data.get("daily") or {}
                if isinstance(last_sent, dict):
                    ledger._last_sent = {
                        str(k): float(v) for k, v in last_sent.items()
                    }
                if isinstance(daily, dict):
                    ledger._daily = {
                        str(site): {str(d): int(c) for d, c in counts.items()}
                        for site, counts in daily.items()
                        if isinstance(counts, dict)
                    }
            except (json.JSONDecodeError, OSError, ValueError, AttributeError, TypeError):
                pass  # file rusak -> mulai dari ledger kosong, jangan gagal total
        return ledger
