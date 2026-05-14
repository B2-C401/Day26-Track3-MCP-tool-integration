import pytest
from implementation.db.errors import ValidationError
from implementation.db.validators import (
    validate_identifier,
    validate_metric,
    ALLOWED_OPERATORS,
    ALLOWED_METRICS,
)


class TestValidateIdentifier:
    @pytest.mark.parametrize("name", ["users", "_x", "col1", "Students", "table_2"])
    def test_accepts_valid_identifier(self, name):
        assert validate_identifier(name) == name

    @pytest.mark.parametrize("bad", [
        "",
        "1foo",
        "foo bar",
        "foo;bar",
        "foo'",
        'foo"',
        "foo-bar",
        "foo;DROP TABLE users",
        "--",
        "OR 1=1",
    ])
    def test_rejects_invalid_identifier(self, bad):
        with pytest.raises(ValidationError):
            validate_identifier(bad)


class TestValidateMetric:
    @pytest.mark.parametrize("m", ["count", "avg", "sum", "min", "max"])
    def test_accepts_lowercase_metric(self, m):
        assert validate_metric(m) == m

    @pytest.mark.parametrize("m", ["COUNT", "Avg", "median", "", "select"])
    def test_rejects_unknown_metric(self, m):
        with pytest.raises(ValidationError):
            validate_metric(m)


def test_operator_whitelist_is_immutable_set():
    assert isinstance(ALLOWED_OPERATORS, frozenset)
    assert "=" in ALLOWED_OPERATORS
    assert "OR" not in ALLOWED_OPERATORS


def test_metric_whitelist_is_immutable_set():
    assert isinstance(ALLOWED_METRICS, frozenset)
    assert ALLOWED_METRICS == frozenset({"count", "avg", "sum", "min", "max"})


class FakeAdapter:
    """Minimal stand-in for an adapter — only the methods validators call."""
    def __init__(self, schema):
        self._schema = schema  # {table: [col, ...]}

    def list_tables(self):
        return list(self._schema)

    def get_table_schema(self, table):
        return [{"name": c} for c in self._schema[table]]


@pytest.fixture
def adapter():
    return FakeAdapter({
        "students": ["id", "name", "cohort", "score"],
        "courses": ["id", "title", "credits"],
    })


class TestValidateTable:
    def test_accepts_known_table(self, adapter):
        from implementation.db.validators import validate_table
        assert validate_table(adapter, "students") == "students"

    def test_rejects_unknown_table(self, adapter):
        from implementation.db.validators import validate_table
        with pytest.raises(ValidationError):
            validate_table(adapter, "ghosts")

    def test_rejects_syntactically_bad_table(self, adapter):
        from implementation.db.validators import validate_table
        with pytest.raises(ValidationError):
            validate_table(adapter, "students;")


class TestValidateColumns:
    def test_accepts_known_columns(self, adapter):
        from implementation.db.validators import validate_columns
        assert validate_columns(adapter, "students", ["id", "name"]) == ["id", "name"]

    def test_rejects_unknown_column(self, adapter):
        from implementation.db.validators import validate_columns
        with pytest.raises(ValidationError):
            validate_columns(adapter, "students", ["id", "ghost"])

    def test_empty_columns_means_all_columns(self, adapter):
        from implementation.db.validators import validate_columns
        assert validate_columns(adapter, "students", None) == ["id", "name", "cohort", "score"]


class TestValidateFilters:
    def test_accepts_valid_filter_list(self, adapter):
        from implementation.db.validators import validate_filters
        filters = [{"column": "cohort", "op": "=", "value": "A1"}]
        assert validate_filters(adapter, "students", filters) == filters

    def test_none_filters_returns_empty(self, adapter):
        from implementation.db.validators import validate_filters
        assert validate_filters(adapter, "students", None) == []

    def test_rejects_bad_operator(self, adapter):
        from implementation.db.validators import validate_filters
        with pytest.raises(ValidationError):
            validate_filters(adapter, "students", [{"column": "id", "op": "OR", "value": 1}])

    def test_rejects_unknown_column(self, adapter):
        from implementation.db.validators import validate_filters
        with pytest.raises(ValidationError):
            validate_filters(adapter, "students", [{"column": "ghost", "op": "=", "value": 1}])

    def test_requires_list_value_for_IN(self, adapter):
        from implementation.db.validators import validate_filters
        with pytest.raises(ValidationError):
            validate_filters(adapter, "students", [{"column": "id", "op": "IN", "value": 1}])


class TestValidateInsertValues:
    def test_accepts_known_columns(self, adapter):
        from implementation.db.validators import validate_insert_values
        vs = {"name": "Anh", "cohort": "A1"}
        assert validate_insert_values(adapter, "students", vs) == vs

    def test_rejects_empty(self, adapter):
        from implementation.db.validators import validate_insert_values
        with pytest.raises(ValidationError):
            validate_insert_values(adapter, "students", {})

    def test_rejects_unknown_column(self, adapter):
        from implementation.db.validators import validate_insert_values
        with pytest.raises(ValidationError):
            validate_insert_values(adapter, "students", {"ghost": 1})
