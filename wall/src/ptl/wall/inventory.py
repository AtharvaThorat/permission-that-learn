"""Tool inventory: which capability each tool has and which arguments name people."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from .models import Capability


class ToolSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    capability: Capability
    target_args: tuple[str, ...] = ()
    attachment_arg: str | None = None
    permission_arg: str | None = None


class ToolInventory(BaseModel):
    model_config = ConfigDict(frozen=True)

    suite: str
    tools: dict[str, ToolSpec]

    def get(self, name: str) -> ToolSpec | None:
        return self.tools.get(name)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ToolInventory":
        return cls._from_dict(yaml.safe_load(Path(path).read_text()))

    @classmethod
    def workspace(cls) -> "ToolInventory":
        """The bundled, hand-labeled inventory for AgentDojo's Workspace suite (loaded once, cached)."""
        return _load_workspace()

    @classmethod
    def _from_dict(cls, data: dict) -> "ToolInventory":
        tools = {
            name: ToolSpec(name=name, **(spec or {}))
            for name, spec in data["tools"].items()
        }
        return cls(suite=data["suite"], tools=tools)


@lru_cache(maxsize=1)
def _load_workspace() -> ToolInventory:
    text = resources.files("ptl.wall").joinpath("workspace_tools.yaml").read_text()
    return ToolInventory._from_dict(yaml.safe_load(text))
