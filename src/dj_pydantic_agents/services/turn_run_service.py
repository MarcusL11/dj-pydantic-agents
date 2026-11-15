"""Run one turn in a worker: claim it, run the agent, save the result."""

import logging
from functools import partial
from typing import TYPE_CHECKING

from dj_pydantic_agents.dtos.turn_commands import ClaimTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import FailTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import SaveTurnResultCommandDTO
from dj_pydantic_agents.dtos.turn_commands import TurnUsageDTO
from dj_pydantic_agents.dtos.turn_events import TurnFinishedEventDTO
from dj_pydantic_agents.errors import AgentNotFound
from dj_pydantic_agents.errors import DjPydanticAgentsError
from dj_pydantic_agents.kit.errors import error_code_for
from dj_pydantic_agents.kit.events import ApprovalRequestedEventDTO
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.kit.events import TurnFailedEventDTO
from dj_pydantic_agents.kit.history import describe_pending
from dj_pydantic_agents.kit.history import messages_from_json
from dj_pydantic_agents.kit.history import messages_to_json
from dj_pydantic_agents.kit.history import pending_from_json
from dj_pydantic_agents.kit.history import pending_to_json
from dj_pydantic_agents.kit.text_combiner import TextCombiner
from dj_pydantic_agents.signals import send_hook
from dj_pydantic_agents.signals import turn_finished

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic_ai.usage import RunUsage

    from dj_pydantic_agents.dtos.turn_commands import RunTurnCommandDTO
    from dj_pydantic_agents.dtos.turn_commands import TurnRunInputDTO
    from dj_pydantic_agents.dtos.turn_commands import TurnSavedResultDTO
    from dj_pydantic_agents.dtos.turn_events import TurnRunStatus
    from dj_pydantic_agents.extensions import DepsFactory
    from dj_pydantic_agents.extensions import EventTransport
    from dj_pydantic_agents.extensions import ModelFactory
    from dj_pydantic_agents.kit.events import TurnEventDTO
    from dj_pydantic_agents.kit.runner import TurnOutcome
    from dj_pydantic_agents.kit.runner import TurnRunner
    from dj_pydantic_agents.kit.specs import AgentSpec
    from dj_pydantic_agents.repositories.turn_command_repository import (
        TurnCommandRepository,
    )

logger = logging.getLogger(__name__)


class TurnRunService:
    def __init__(  # noqa: PLR0913
        self,
        *,
        repository: TurnCommandRepository,
        specs: Mapping[str, AgentSpec],
        deps_factory: DepsFactory,
        model_factory: ModelFactory,
        transport: EventTransport,
        runner: TurnRunner,
    ) -> None:
        self._repository = repository
        self._specs = specs
        self._deps_factory = deps_factory
        self._model_factory = model_factory
        self._transport = transport
        self._runner = runner

    def run_turn(self, *, command: RunTurnCommandDTO) -> None:
        """Run a queued turn. A failure records its code and does not raise."""
        run_input = self._repository.claim_turn(
            command=ClaimTurnCommandDTO(turn_id=command.turn_id),
        )
        if run_input is None:
            logger.info("Turn %s is not in the queue. Skip it.", command.turn_id)
            return

        try:
            saved, final_event = self._run_and_save(run_input=run_input)
        except Exception as error:  # noqa: BLE001 - each error fails the turn
            self._fail(run_input=run_input, error=error)
            return
        self._publish(run_input.turn_id, final_event)
        self._send_finished(run_input=run_input, status=saved.status, error_code="")

    def _run_and_save(
        self,
        *,
        run_input: TurnRunInputDTO,
    ) -> tuple[TurnSavedResultDTO, TurnEventDTO]:
        outcome = self._run(run_input=run_input)
        pending = outcome.pending_approvals
        saved = self._repository.save_turn_result(
            command=SaveTurnResultCommandDTO(
                turn_id=run_input.turn_id,
                new_messages=tuple(messages_to_json(list(outcome.new_messages))),
                pending=pending_to_json(pending),
                approvals=describe_pending(pending) if pending is not None else (),
                usage=_usage(outcome.usage),
            ),
        )
        if pending is not None:
            return saved, ApprovalRequestedEventDTO(approvals=describe_pending(pending))
        return saved, TurnDoneEventDTO(text=outcome.reply_text or "")

    def _run(self, *, run_input: TurnRunInputDTO) -> TurnOutcome:
        spec = self._specs.get(run_input.agent_name)
        if spec is None:
            msg = f"No agent has the name {run_input.agent_name!r}."
            raise AgentNotFound(msg)
        deps = self._deps_factory(
            agent_name=run_input.agent_name,
            user_id=run_input.user_id,
            conversation_id=run_input.conversation_id,
        )
        model = self._model_factory.build(
            role=spec.model_role,
            user_id=run_input.user_id,
        )
        combiner = TextCombiner(partial(self._publish, run_input.turn_id))
        try:
            return self._runner.run(
                spec=spec,
                model=model,
                history=messages_from_json(list(run_input.history)),
                prompt=run_input.prompt,
                pending=pending_from_json(run_input.pending),
                decisions=run_input.decisions,
                deps=deps,
                on_event=combiner,
            )
        finally:
            # The waiting text goes before the final event, also after an error.
            combiner.flush()

    def _fail(self, *, run_input: TurnRunInputDTO, error: Exception) -> None:
        error_code = _error_code(error)
        logger.error(
            "Turn %s failed with %s.",
            run_input.turn_id,
            error_code,
            exc_info=error,
        )
        self._repository.fail_turn(
            command=FailTurnCommandDTO(
                turn_id=run_input.turn_id,
                error_code=error_code,
            ),
        )
        self._publish(run_input.turn_id, TurnFailedEventDTO(error_code=error_code))
        self._send_finished(
            run_input=run_input,
            status="failed",
            error_code=error_code,
        )

    def _publish(self, turn_id: str, event: TurnEventDTO) -> None:
        """Publish an event. Log a transport error, so that it cannot stop a turn.

        The database is the record of the turn. A page reload shows the result.
        """
        try:
            self._transport.publish(turn_id=turn_id, event=event)
        except Exception:
            logger.exception("Turn %s lost a %s event.", turn_id, event.kind)

    def _send_finished(
        self,
        *,
        run_input: TurnRunInputDTO,
        status: TurnRunStatus,
        error_code: str,
    ) -> None:
        send_hook(
            turn_finished,
            sender=type(self),
            event=TurnFinishedEventDTO(
                turn_id=run_input.turn_id,
                conversation_id=run_input.conversation_id,
                agent_name=run_input.agent_name,
                user_id=run_input.user_id,
                status=status,
                error_code=error_code,
            ),
        )


def _error_code(error: Exception) -> str:
    """The code of a package error, else the code of a Pydantic AI error."""
    if isinstance(error, DjPydanticAgentsError) and error.error_code:
        return error.error_code
    return error_code_for(error)


def _usage(usage: RunUsage) -> TurnUsageDTO:
    return TurnUsageDTO(
        requests=usage.requests,
        tool_calls=usage.tool_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        output_reasoning_tokens=usage.output_reasoning_tokens,
    )
