"""Read the conversation pages."""

# create_autospec() reads the annotations of each method, so the annotation
# types load at runtime.
# ruff: noqa: TC001

from dj_pydantic_agents.dtos.conversation_queries import ConversationPageProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import (
    ConversationSummaryProjectionDTO,
)
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import ListConversationsQueryDTO
from dj_pydantic_agents.dtos.turn_commands import UserId
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.extensions import AgentPermission
from dj_pydantic_agents.extensions import PromptFiles
from dj_pydantic_agents.kit.attachments import FileRefDTO
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)


class ConversationQueryService:
    def __init__(
        self,
        *,
        repository: ConversationQueryRepository,
        permission: AgentPermission,
        prompt_files: PromptFiles | None = None,
    ) -> None:
        self._repository = repository
        self._permission = permission
        # The project store of the message files. None: the chat takes no files.
        self._prompt_files = prompt_files

    def list_conversations(
        self,
        *,
        query: ListConversationsQueryDTO,
    ) -> tuple[ConversationSummaryProjectionDTO, ...]:
        """The conversations of the user with the agent, newest first."""
        self._check_access(user_id=query.user_id, agent_name=query.agent_name)
        return self._repository.list_conversations(query=query)

    def get_conversation_page(
        self,
        *,
        query: GetConversationPageQueryDTO,
    ) -> ConversationPageProjectionDTO:
        """Only a user who can still use the agent can read the conversation.

        With PROMPT_FILES, the page also gets the pending files, and the size
        and URL of each file in the transcript.
        """
        page = self._repository.get_conversation_page(query=query)
        self._check_access(user_id=query.user_id, agent_name=page.agent_name)
        if self._prompt_files is None:
            return page
        return page.model_copy(
            update={
                "lines": _described_lines(page.lines, prompt_files=self._prompt_files),
                "pending_files": self._prompt_files.pending(
                    conversation_id=page.conversation_id,
                    user_id=query.user_id,
                ),
            },
        )

    def _check_access(self, *, user_id: UserId, agent_name: str) -> None:
        if not self._permission.can_use(user_id=user_id, agent_name=agent_name):
            msg = f"The user cannot use the agent {agent_name!r}."
            raise AgentAccessDenied(msg)


def _described_lines(
    lines: tuple[TranscriptLineDTO, ...],
    *,
    prompt_files: PromptFiles,
) -> tuple[TranscriptLineDTO, ...]:
    """Put the project data in each file of the lines.

    A transcript with no file needs no call. A file that the project does not
    know keeps the name and the type from the history.
    """
    file_ids = tuple(file.file_id for line in lines for file in line.files)
    if not file_ids:
        return lines
    described = {
        file.file_id: file for file in prompt_files.describe(file_ids=file_ids)
    }
    return tuple(
        line.model_copy(
            update={"files": tuple(_described(file, described) for file in line.files)},
        )
        if line.files
        else line
        for line in lines
    )


def _described(file: FileRefDTO, described: dict[str, FileRefDTO]) -> FileRefDTO:
    return described.get(file.file_id, file)
