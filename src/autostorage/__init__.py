"""Interface for database storage."""

__version__ = "0.0.8"

from . import database, models, read, select, utils
from .database import Database

__all__ = ["Database", "database", "iterator", "models", "read", "select", "utils"]
