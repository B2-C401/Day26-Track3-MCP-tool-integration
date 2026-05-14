import pytest

from implementation.db.errors import ValidationError
from ._adapter_contract import AdapterContract


class TestSQLiteContract(AdapterContract):
    @pytest.fixture
    def adapter(self, sqlite_adapter):
        return sqlite_adapter
