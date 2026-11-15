from enum import StrEnum


class ModelRole(StrEnum):
    """The job of a model. The model factory builds one model for each role."""

    CHAT = "chat"
    SUMMARY = "summary"
