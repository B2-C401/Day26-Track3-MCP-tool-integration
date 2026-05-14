"""Database adapter layer. SQL stays here; MCP stays out."""

from .base import DatabaseAdapter
from .errors import AdapterError, DBError, ValidationError

__all__ = ["DatabaseAdapter", "DBError", "ValidationError", "AdapterError"]
