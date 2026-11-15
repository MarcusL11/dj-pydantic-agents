"""Prefixed ULID keys, for example cnv_01m7f5c8m8xzp0zy3vmbgzbdw9.

The prefix shows the type of a key in a log, a stream key or a URL. The ULID
part sorts by time. Migrations refer to each generator by its name, so add a
new prefix here and never rename one.
"""

from ulid import ULID

# The prefix, the underscore and the 26 characters of a ULID.
ID_LENGTH = 30


def prefixed_ulid(prefix: str) -> str:
    return f"{prefix}_{str(ULID()).lower()}"


def new_conversation_id() -> str:
    return prefixed_ulid("cnv")


def new_turn_id() -> str:
    return prefixed_ulid("trn")


def new_approval_id() -> str:
    return prefixed_ulid("apr")
