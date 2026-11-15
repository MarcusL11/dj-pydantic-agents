from dataclasses import dataclass
from typing import TYPE_CHECKING

from dj_pydantic_agents.kit.roles import ModelRole

if TYPE_CHECKING:
    from pydantic_ai.capabilities import AbstractCapability
    from pydantic_ai.toolsets import AbstractToolset


@dataclass(frozen=True, kw_only=True)
class AgentSpec:
    """The parts of one agent that a project gives to the package.

    This is a dataclass, not a DTO, because it holds Pydantic AI objects.
    """

    name: str
    instructions: str
    model_role: ModelRole = ModelRole.CHAT
    deps_type: type = object
    toolsets: tuple[AbstractToolset[object], ...] = ()
    capabilities: tuple[AbstractCapability[object], ...] = ()
