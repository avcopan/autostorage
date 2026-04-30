"""Types for database row fields."""

from enum import StrEnum


class Role(StrEnum):
    """Calculation geometry roles."""

    input = "input"
    output = "output"
