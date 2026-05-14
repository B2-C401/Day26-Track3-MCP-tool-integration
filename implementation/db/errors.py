"""Database layer exceptions, decoupled from FastMCP."""


class DBError(Exception):
    """Base for adapter-related failures."""


class ValidationError(DBError):
    """Raised when user input cannot be safely turned into SQL."""


class AdapterError(DBError):
    """Raised when the underlying database driver fails."""
