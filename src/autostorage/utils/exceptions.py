"""Custom Exceptions."""


class KeyRelationshipNotEstablishedError(Exception):
    """Raise an error when a key relationship could not be established."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
