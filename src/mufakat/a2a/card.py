"""Agent Card A2A (format sesuai spesifikasi A2A).

Agent Card adalah dokumen JSON yang mendeskripsikan kemampuan
sebuah agent: nama, URL, skill, dan skema autentikasi. Modul ini
hanya membangun dan memvalidasi card — tidak ada klaim bahwa
agent eksternal mana pun sudah membaca card ini.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentSkill(BaseModel):
    """Satu skill yang ditawarkan agent."""

    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class AgentCapability(BaseModel):
    """Kapabilitas agent (streaming, push notification, state)."""

    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = False


class AgentCard(BaseModel):
    """Agent Card A2A."""

    name: str = Field(..., min_length=1)
    description: str = ""
    url: str = Field(..., min_length=1)
    version: str = "0.1.0"
    capabilities: AgentCapability = Field(default_factory=AgentCapability)
    skills: list[AgentSkill] = Field(default_factory=list)
    default_input_modes: list[str] = Field(default_factory=lambda: ["text"])
    default_output_modes: list[str] = Field(default_factory=lambda: ["text"])
    authentication: list[dict] = Field(default_factory=list)

    def to_json(self) -> str:
        """Serialisasi card ke JSON."""
        return self.model_dump_json(indent=2, exclude_none=True)

    @classmethod
    def from_json(cls, data: str) -> "AgentCard":
        """Parse card dari JSON (validasi penuh)."""
        return cls.model_validate_json(data)


def create_agent_card(name: str, url: str, description: str = "",
                      skills: list[AgentSkill] | None = None,
                      version: str = "0.1.0") -> AgentCard:
    """Buat Agent Card MUFAKAT untuk satu agent/peran."""
    return AgentCard(
        name=name, description=description, url=url, version=version,
        skills=list(skills or []),
        capabilities=AgentCapability(streaming=False, push_notifications=False,
                                     state_transition_history=True),
    )
