"""Plain Pydantic domain classes that the table rows inherit from."""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

__all__ = ["Calculation", "Model"]

# The rows' JSON columns are nullable, so a stored row may hold `None` here; the
# domain classes read it as an empty dict.
_Dict = Annotated[dict[str, Any], BeforeValidator(lambda v: {} if v is None else v)]


class Model(BaseModel):
    """An electronic-structure model: what determines a calculation's result."""

    program: str
    program_version: str | None = None
    method: str
    basis: str | None = None
    keywords: _Dict = Field(default_factory=dict)
    """Electronic-structure keywords only; optimizer keywords go in
    `Calculation.input_provenance`. `None` is read as ``{}``."""


class Calculation(BaseModel):
    """A calculation run with some model; the model is paired separately."""

    calc_type: str
    input_provenance: _Dict = Field(default_factory=dict)
    """Everything else about how it was run (e.g. optimizer keywords); not hashed.
    `None` is read as ``{}``."""
    output_provenance: _Dict = Field(default_factory=dict)
    """How the output was produced. `None` is read as ``{}``."""
