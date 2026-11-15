"""These tests use the Redis server of compose.yml. Start it: docker compose up -d"""

import asyncio
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from redis import Redis

from dj_pydantic_agents.ids import new_turn_id
from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.transports import redis_stream
from dj_pydantic_agents.transports.redis_stream import STREAM_TTL_SECONDS
from dj_pydantic_agents.transports.redis_stream import RedisStreamTransport
from dj_pydantic_agents.transports.redis_stream import stream_key
from tests.testcases import SimpleTestCase


class TestRedisStreamTransport(SimpleTestCase):
    def setUp(self):
        self.turn_id = new_turn_id()
        self.transport = RedisStreamTransport()
        self.redis = Redis.from_url(
            settings.DJ_PYDANTIC_AGENTS["REDIS_URL"],
            decode_responses=True,
        )
        self.addCleanup(self.redis.close)
        self.addCleanup(self.redis.delete, stream_key(self.turn_id))

    def publish(self, *events):
        return [
            self.transport.publish(turn_id=self.turn_id, event=event)
            for event in events
        ]

    async def read_all(self, after_id="0"):
        return [
            streamed
            async for streamed in self.transport.read(
                turn_id=self.turn_id,
                after_id=after_id,
            )
        ]

    def test_publish_returns_the_stream_id_and_sets_the_ttl(self):
        [event_id] = self.publish(TextDeltaEventDTO(text="Hi"))

        [(stored_id, _)] = self.redis.xrange(stream_key(self.turn_id)) or []
        assert event_id == stored_id
        assert 0 < self.redis.ttl(stream_key(self.turn_id)) <= STREAM_TTL_SECONDS

    async def test_read_yields_the_events_and_stops_after_the_final_event(self):
        first = TextDeltaEventDTO(text="Hi")
        done = TurnDoneEventDTO(text="Hi")
        ids = self.publish(first, done, TextDeltaEventDTO(text="late"))

        streamed = await self.read_all()

        assert [(item.event_id, item.event) for item in streamed] == [
            (ids[0], first),
            (ids[1], done),
        ]

    async def test_read_starts_after_the_event_id(self):
        done = TurnDoneEventDTO(text="Hi")
        ids = self.publish(TextDeltaEventDTO(text="Hi"), done)

        streamed = await self.read_all(after_id=ids[0])

        assert [item.event for item in streamed] == [done]

    async def test_read_yields_none_when_no_event_comes(self):
        reader = self.transport.read(turn_id=self.turn_id, after_id="0")

        with mock.patch.object(redis_stream, "BLOCK_MILLISECONDS", 10):
            first = await anext(reader)
        await reader.aclose()

        assert first is None

    async def test_read_logs_and_skips_a_bad_entry(self):
        key = stream_key(self.turn_id)
        self.redis.xadd(key, {"event": "not json"})
        self.redis.xadd(key, {"other": "field"})
        done = TurnDoneEventDTO(text="Hi")
        self.publish(done)

        with self.assertLogs(redis_stream.logger, "WARNING") as logs:
            streamed = await self.read_all()

        assert [item.event for item in streamed] == [done]
        assert len(logs.records) == 2  # noqa: PLR2004

    async def test_a_bad_last_entry_does_not_stop_the_read(self):
        self.redis.xadd(stream_key(self.turn_id), {"event": "not json"})
        reader = self.transport.read(turn_id=self.turn_id, after_id="0")

        # Without a move of last_id, XREAD returns the bad entry again and again.
        with (
            mock.patch.object(redis_stream, "BLOCK_MILLISECONDS", 10),
            self.assertLogs(redis_stream.logger, "WARNING"),
        ):
            async with asyncio.timeout(2):
                first = await anext(reader)
        await reader.aclose()

        assert first is None

    def test_needs_a_redis_url(self):
        values = {**settings.DJ_PYDANTIC_AGENTS, "REDIS_URL": None}

        with (
            override_settings(DJ_PYDANTIC_AGENTS=values),
            self.assertRaisesRegex(ImproperlyConfigured, "REDIS_URL"),
        ):
            RedisStreamTransport()
