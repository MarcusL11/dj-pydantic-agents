"""The work that each task runner calls."""

from dj_pydantic_agents.composition import build_turn_run_service
from dj_pydantic_agents.dtos.turn_commands import RunTurnCommandDTO


def run_turn(turn_id: str) -> None:
    """Run one queued turn. It does not raise for a failed turn."""
    build_turn_run_service().run_turn(command=RunTurnCommandDTO(turn_id=turn_id))
