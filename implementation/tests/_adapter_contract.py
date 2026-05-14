"""Shared assertions for any DatabaseAdapter. Subclassed by SQLite + Postgres tests."""

import pytest

from implementation.db.errors import ValidationError


class AdapterContract:
    def test_list_tables(self, adapter):
        tables = set(adapter.list_tables())
        assert {"students", "courses", "enrollments"} <= tables

    def test_get_table_schema_students(self, adapter):
        cols = {c["name"] for c in adapter.get_table_schema("students")}
        assert cols == {"id", "name", "cohort", "score"}

    def test_get_full_schema_has_all_tables(self, adapter):
        full = adapter.get_full_schema()
        assert {"students", "courses", "enrollments"} <= set(full)
        assert any(c["name"] == "name" for c in full["students"])

    # --- search ---

    def test_search_returns_all_columns_by_default(self, adapter):
        result = adapter.search("students", limit=3)
        assert result["table"] == "students"
        assert set(result["columns"]) == {"id", "name", "cohort", "score"}
        assert len(result["rows"]) == 3
        assert result["limit"] == 3 and result["offset"] == 0

    def test_search_projects_columns(self, adapter):
        result = adapter.search("students", columns=["name", "cohort"], limit=1)
        assert set(result["rows"][0]) == {"name", "cohort"}

    def test_search_filter_equals(self, adapter):
        result = adapter.search(
            "students",
            filters=[{"column": "cohort", "op": "=", "value": "A1"}],
            limit=50,
        )
        assert all(r["cohort"] == "A1" for r in result["rows"])
        assert len(result["rows"]) == 4

    def test_search_filter_in(self, adapter):
        result = adapter.search(
            "students",
            filters=[{"column": "cohort", "op": "IN", "value": ["A1", "B2"]}],
            limit=50,
        )
        assert len(result["rows"]) == 10

    def test_search_filter_like(self, adapter):
        result = adapter.search(
            "students",
            filters=[{"column": "name", "op": "LIKE", "value": "A%"}],
        )
        assert all(r["name"].startswith("A") for r in result["rows"])

    def test_search_order_by_descending(self, adapter):
        result = adapter.search("students", order_by="score", descending=True, limit=3)
        scores = [r["score"] for r in result["rows"]]
        assert scores == sorted(scores, reverse=True)

    def test_search_pagination_has_more(self, adapter):
        page1 = adapter.search("students", limit=5, offset=0)
        page2 = adapter.search("students", limit=5, offset=5)
        assert page1["has_more"] is True
        assert page2["has_more"] in (False, True)
        ids = {r["id"] for r in page1["rows"]} | {r["id"] for r in page2["rows"]}
        assert len(ids) == 10

    def test_search_rejects_unknown_table(self, adapter):
        with pytest.raises(ValidationError):
            adapter.search("ghosts")

    def test_search_rejects_unknown_column(self, adapter):
        with pytest.raises(ValidationError):
            adapter.search("students", columns=["ghost"])

    def test_search_rejects_bad_operator(self, adapter):
        with pytest.raises(ValidationError):
            adapter.search("students", filters=[{"column": "id", "op": "OR", "value": 1}])

    def test_search_clamps_limit(self, adapter):
        result = adapter.search("students", limit=10_000)
        assert result["limit"] == 200
        result2 = adapter.search("students", limit=0)
        assert result2["limit"] == 1

    # --- insert ---

    def test_insert_returns_payload_with_id(self, adapter):
        result = adapter.insert("students", {"name": "Zen", "cohort": "A1", "score": 7.5})
        assert result["table"] == "students"
        assert result["inserted"]["name"] == "Zen"
        assert isinstance(result["id"], int) and result["id"] > 0

    def test_insert_is_visible_to_search(self, adapter):
        adapter.insert("students", {"name": "Mai", "cohort": "C3", "score": 8.0})
        found = adapter.search(
            "students",
            filters=[{"column": "cohort", "op": "=", "value": "C3"}],
        )
        assert any(r["name"] == "Mai" for r in found["rows"])

    def test_insert_rejects_empty(self, adapter):
        with pytest.raises(ValidationError):
            adapter.insert("students", {})

    def test_insert_rejects_unknown_column(self, adapter):
        with pytest.raises(ValidationError):
            adapter.insert("students", {"ghost": 1})

    def test_insert_rejects_unknown_table(self, adapter):
        with pytest.raises(ValidationError):
            adapter.insert("ghosts", {"x": 1})

    # --- aggregate ---

    def test_aggregate_count_all(self, adapter):
        result = adapter.aggregate("students", "count")
        assert result["metric"] == "count"
        assert result["rows"] == [{"group": None, "value": 10}]

    def test_aggregate_avg_score(self, adapter):
        result = adapter.aggregate("students", "avg", column="score")
        assert result["metric"] == "avg"
        assert len(result["rows"]) == 1
        assert 0 < result["rows"][0]["value"] < 10

    def test_aggregate_sum_min_max(self, adapter):
        for metric, expected_check in [
            ("sum", lambda v: v > 0),
            ("min", lambda v: v == 5.5),
            ("max", lambda v: v == 9.2),
        ]:
            result = adapter.aggregate("students", metric, column="score")
            assert expected_check(result["rows"][0]["value"]), (metric, result)

    def test_aggregate_group_by_cohort(self, adapter):
        result = adapter.aggregate("students", "avg", column="score", group_by="cohort")
        groups = {r["group"]: r["value"] for r in result["rows"]}
        assert set(groups) == {"A1", "B2"}

    def test_aggregate_count_with_filter(self, adapter):
        result = adapter.aggregate(
            "students", "count",
            filters=[{"column": "cohort", "op": "=", "value": "A1"}],
        )
        assert result["rows"][0]["value"] == 4

    def test_aggregate_rejects_unknown_metric(self, adapter):
        with pytest.raises(ValidationError):
            adapter.aggregate("students", "median", column="score")

    def test_aggregate_requires_column_for_avg(self, adapter):
        with pytest.raises(ValidationError):
            adapter.aggregate("students", "avg")

    def test_aggregate_rejects_unknown_column(self, adapter):
        with pytest.raises(ValidationError):
            adapter.aggregate("students", "avg", column="ghost")
