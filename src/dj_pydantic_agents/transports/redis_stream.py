"""Store the events of each turn in a Redis Stream, one stream for each turn.

A worker publishes with the sync client. A stream view reads with the async
client, so that a wait for a new event does not hold a thread.
"""

import logging
from functools import cache
from typing import TYPE_CHECKING
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from pydantic import ValidationError
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from dj_pydantic_agents.conf import SETTING_NAME
from dj_pydantic_agents.conf import load_settings
from dj_pydantic_agents.kit.events import START_EVENT_ID
from dj_pydantic_agents.kit.events import TURN_EVENT_ADAPTER
from dj_pydantic_agents.kit.events import StreamedTurnEventDTO

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from dj_pydantic_agents.kit.events import TurnEventDTO

logger = logging.getLogger(__name__)

KEY_PREFIX = "dj_pydantic_agents:turn:"
EVENT_FIELD = "event"
# Each event sets the time to live again. The database keeps the turn.
STREAM_TTL_SECONDS = 3600
# Redis trims each stream to about this number of events.
STREAM_MAX_LENGTH = 10_000
# After this wait with no event, read() yields None for a keep-alive.
BLOCK_MILLISECONDS = 15_000
READ_COUNT = 50


def stream_key(turn_id: str) -> str:
    return f"{KEY_PREFIX}{turn_id}"


class RedisStreamTransport:
    def __init__(self) -> None:
        self._url = _redis_url()

    def publish(self, *, turn_id: str, event: TurnEventDTO) -> str:
        key = stream_key(turn_id)
        pipeline = _sync_client(self._url).pipeline(transaction=True)
        pipeline.xadd(
            key,
            {EVENT_FIELD: TURN_EVENT_ADAPTER.dump_json(event)},
            maxlen=STREAM_MAX_LENGTH,
            approximate=True,
        )
        pipeline.expire(key, STREAM_TTL_SECONDS)
        event_id, _ = pipeline.execute()
        return str(event_id)

    async def read(
        self,
        *,
        turn_id: str,
        after_id: str = START_EVENT_ID,
    ) -> AsyncGenerator[StreamedTurnEventDTO | None]:
        key = stream_key(turn_id)
        client = AsyncRedis.from_url(self._url, decode_responses=True)
        last_id = after_id
        try:
            while True:
                # The types of redis cover each reply shape. This client gets
                # the RESP2 shape with str values: [[key, [(id, fields), ...]]].
                reply: Any = await client.xread(
                    {key: last_id},
                    count=READ_COUNT,
                    block=BLOCK_MILLISECONDS,
                )
                if not reply:
                    yield None
                    continue
                for event_id, fields in reply[0][1]:
                    # A bad entry also moves last_id, so that XREAD skips it.
                    last_id = event_id
                    streamed = _parse_entry(
                        turn_id=turn_id,
                        event_id=event_id,
                        fields=fields,
                    )
                    if streamed is not None:
                        yield streamed
                        if streamed.is_final:
                            return
        finally:
            await client.aclose()


def _redis_url() -> str:
    if url := load_settings().redis_url:
        return url
    msg = f"{SETTING_NAME} needs REDIS_URL for the Redis transport."
    raise ImproperlyConfigured(msg)


@cache
def _sync_client(url: str) -> Redis:
    """Keep one connection pool for each URL in a process."""
    return Redis.from_url(url, decode_responses=True)


def _parse_entry(
    *,
    turn_id: str,
    event_id: str,
    fields: dict[str, str],
) -> StreamedTurnEventDTO | None:
    try:
        event = TURN_EVENT_ADAPTER.validate_json(fields[EVENT_FIELD])
    except KeyError, ValidationError:
        logger.warning("Turn %s has a bad event %s. Skip it.", turn_id, event_id)
        return None
    return StreamedTurnEventDTO(event_id=event_id, event=event)
