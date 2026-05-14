import pytest
from fastmcp import Client

from implementation.mcp_server import build_server
from implementation.db.sqlite_adapter import SQLiteAdapter


@pytest.fixture
def server(seeded_sqlite_path):
    adapter = SQLiteAdapter(str(seeded_sqlite_path))
    server = build_server(adapter)
    yield server
    adapter.close()


@pytest.fixture
async def client(server):
    async with Client(server) as c:
        yield c


class TestToolDiscovery:
    async def test_three_tools_exposed(self, client):
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert names == {"search", "insert", "aggregate"}


class TestSearchTool:
    async def test_happy(self, client):
        result = await client.call_tool(
            "search",
            {"table": "students", "filters": [{"column": "cohort", "op": "=", "value": "A1"}]},
        )
        assert result.data["table"] == "students"
        assert len(result.data["rows"]) == 4

    async def test_unknown_table_error(self, client):
        with pytest.raises(Exception) as exc:
            await client.call_tool("search", {"table": "ghosts"})
        assert "validation" in str(exc.value).lower()


class TestInsertTool:
    async def test_happy_and_visible_to_search(self, client):
        ins = await client.call_tool(
            "insert",
            {"table": "students", "values": {"name": "ToolUser", "cohort": "Z9", "score": 10.0}},
        )
        assert ins.data["id"] > 0

        srch = await client.call_tool(
            "search",
            {"table": "students", "filters": [{"column": "cohort", "op": "=", "value": "Z9"}]},
        )
        assert any(r["name"] == "ToolUser" for r in srch.data["rows"])

    async def test_empty_values_error(self, client):
        with pytest.raises(Exception) as exc:
            await client.call_tool("insert", {"table": "students", "values": {}})
        assert "validation" in str(exc.value).lower()


class TestAggregateTool:
    async def test_count_all(self, client):
        result = await client.call_tool("aggregate", {"table": "students", "metric": "count"})
        assert result.data["rows"][0]["value"] >= 10

    async def test_avg_by_group(self, client):
        result = await client.call_tool(
            "aggregate",
            {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
        )
        groups = {r["group"] for r in result.data["rows"]}
        assert {"A1", "B2"} <= groups

    async def test_invalid_metric_error(self, client):
        with pytest.raises(Exception) as exc:
            await client.call_tool(
                "aggregate", {"table": "students", "metric": "median", "column": "score"}
            )
        assert "validation" in str(exc.value).lower()
