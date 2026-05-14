"""Abstract interface that SQLiteAdapter and PostgresAdapter both implement."""

from abc import ABC, abstractmethod
from typing import Any


class DatabaseAdapter(ABC):
    @abstractmethod
    def list_tables(self) -> list[str]: ...

    @abstractmethod
    def get_table_schema(self, table: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_full_schema(self) -> dict[str, list[dict[str, Any]]]: ...

    @abstractmethod
    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[dict] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> dict: ...

    @abstractmethod
    def insert(self, table: str, values: dict) -> dict: ...

    @abstractmethod
    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: list[dict] | None = None,
        group_by: str | None = None,
    ) -> dict: ...

    @abstractmethod
    def close(self) -> None: ...
