import json
import pytest
from fastmcp import Client

from implementation.mcp_server import build_server
from implementation.db.sqlite_adapter import SQLiteAdapter


@pytest.fixture
def server(seeded_sqlite_path):
    adapter = SQLiteAdapter(str(seeded_sqlite_path))
    yield build_server(adapter)
    adapter.close()


@pytest.fixture
async def client(server):
    async with Client(server) as c:
        yield c


class TestResourceDiscovery:
    async def test_database_resource_listed(self, client):
        resources = await client.list_resources()
        uris = {str(r.uri) for r in resources}
        assert "schema://database" in uris

    async def test_table_template_listed(self, client):
        templates = await client.list_resource_templates()
        uris = {str(t.uriTemplate) for t in templates}
        assert "schema://table/{table_name}" in uris


class TestReadResources:
    async def test_full_schema(self, client):
        res = await client.read_resource("schema://database")
        text = res[0].text
        data = json.loads(text)
        assert "tables" in data
        assert {"students", "courses", "enrollments"} <= set(data["tables"])

    async def test_single_table_schema(self, client):
        res = await client.read_resource("schema://table/students")
        text = res[0].text
        data = json.loads(text)
        assert data["table"] == "students"
        names = {c["name"] for c in data["columns"]}
        assert names == {"id", "name", "cohort", "score"}

    async def test_unknown_table_errors(self, client):
        with pytest.raises(Exception):
            await client.read_resource("schema://table/ghosts")
