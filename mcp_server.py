"""MCP server: exposes our tools to any MCP client (here, the agent in src/agent.py).

The agent starts this file by itself, you do not need to run it.
To test it alone:  mcp dev mcp_server.py   (opens the MCP Inspector in the browser)
"""

from mcp.server.fastmcp import FastMCP

from src.retriever import search_schema
from src.sql_tools import run_sql as run_sql_readonly

mcp = FastMCP("sql-analyst", log_level="WARNING")


@mcp.tool()
def explain_schema(db_id: str, question: str) -> dict:
    """Return the tables of database `db_id` that are relevant to `question`,
    with their columns, descriptions and the source file of each description.
    Always call this before writing SQL."""
    documents = search_schema(db_id, question)
    return {
        "tables": [
            {"table": d.metadata["table"], "schema": d.page_content, "source": d.metadata["source"]}
            for d in documents
        ]
    }


@mcp.tool()
def run_sql(db_id: str, sql: str) -> dict:
    """Run ONE read-only SQLite SELECT query on database `db_id`.
    Anything else is refused. If `ok` is false, read `error`, fix the query and try again."""
    return run_sql_readonly(db_id, sql)


if __name__ == "__main__":
    mcp.run(transport="stdio")
