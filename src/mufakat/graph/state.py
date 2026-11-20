"""RunState MUFAKAT (T7) — state graph berbasis Pydantic.

Sengaja TIDAK mengimpor langgraph di sini: state harus tetap bisa
dipakai (dan diuji) tanpa langgraph terpasang. Bila pydantic belum
terpasang, dipakai shim minimal yang perilakunya setara untuk
keperluan modul ini (``__init__`` kwargs, ``model_dump``,
``model_copy(update=...)``).
"""

from __future__ import annotations

try:  # Jalur normal: pydantic tersedia (lihat pyproject.toml).
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - shim darurat tanpa pydantic
    def Field(default=None, default_factory=None):  # type: ignore
        return default_factory() if default_factory is not None else default

    class BaseModel:  # type: ignore
        def __init__(self, **kwargs):
            cls = type(self)
            for name, ann in getattr(cls, "__annotations__", {}).items():
                default = getattr(cls, name, None)
                value = kwargs.pop(name, None)
                if value is None:
                    value = default() if callable(default) and name in (
                        "messages", "findings", "dissent", "hash_history",
                        "finding_counts",
                    ) else default
                setattr(self, name, value)
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self):
            out = {}
            for name in getattr(type(self), "__annotations__", {}):
                out[name] = getattr(self, name, None)
            return out

        def model_copy(self, update=None):
            data = self.model_dump()
            if update:
                data.update(update)
            return type(self)(**data)


class RunState(BaseModel):
    """State satu run MUFAKAT."""

    run_id: str
    idea: str
    round: int = 1
    phase: str = "research"
    messages: list[dict] = Field(default_factory=list)
    spec: str = ""
    diff_hash: str = ""
    findings: list[dict] = Field(default_factory=list)
    fix_iterations: int = 0
    total_iterations: int = 0
    status: str = "running"
    dissent: list[str] = Field(default_factory=list)
    budget_used: float = 0.0
    approved_spec: bool = False
    approved_commit: bool = False
    # Riwayat tambahan untuk edges (T7): hash diff+temuan yang pernah
    # dilihat dan jumlah temuan per iterasi. Dipakai track_hash() dan
    # should_revise() di graph/edges.py.
    hash_history: list[str] = Field(default_factory=list)
    finding_counts: list[int] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "RunState":
        known = set(cls.model_fields) if hasattr(cls, "model_fields") else set(
            cls.__annotations__
        )
        return cls(**{k: v for k, v in data.items() if k in known})
