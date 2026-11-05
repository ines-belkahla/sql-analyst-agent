"""The SQL analyst agent: an LLM (Groq) that calls our MCP tools in a loop.

create_agent builds a LangGraph graph: model -> tool -> model -> ... until the
model answers without calling a tool. The checkpointer stores the conversation
per thread_id, so follow-up questions ("and for 2012?") keep the context.
"""

import json
import sys

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from src.config import GROQ_MODEL, ROOT

SYSTEM_PROMPT = """You are a data analyst. You answer questions about the SQLite database "{db_id}".

Steps:
1. Call explain_schema with db_id="{db_id}" to find the relevant tables.
2. Write ONE SQLite SELECT query and call run_sql with db_id="{db_id}".
3. If run_sql returns an error or no rows, fix the query and try again (at most 3 tries).
4. Answer in 2-4 sentences, then show the SQL you used, then list the sources
   (the "source" files returned by explain_schema for the tables you used).

Rules:
- Never modify data. If the user asks to insert, update or delete, refuse politely.
- If the database does not contain the information, say so instead of guessing.
- For a follow-up question, reuse the context of the previous questions."""

MCP_SERVERS = {
    "sql": {
        "command": sys.executable,
        "args": [str(ROOT / "mcp_server.py")],
        "transport": "stdio",
    }
}


def get_llm():
    # max_retries: the free Groq tier has rate limits, retry instead of failing
    return ChatGroq(model=GROQ_MODEL, temperature=0, max_retries=5)


def tool_output(message):
    """MCP tool results arrive as JSON text: turn them back into a dict."""
    content = message.content
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return {}


async def run_agent(tools, question, db_id, thread_id, checkpointer):
    """Ask one question and return the answer, the SQL, the result table and the sources."""
    agent = create_agent(
        get_llm(), tools, system_prompt=SYSTEM_PROMPT.format(db_id=db_id), checkpointer=checkpointer
    )
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 15}
    state = await agent.ainvoke({"messages": [HumanMessage(question)]}, config)

    # keep only the messages of this turn (the state also holds earlier turns)
    messages = state["messages"]
    last_question = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
    turn = messages[last_question + 1:]

    result = {"answer": "", "sql": None, "columns": [], "rows": [], "sources": [],
              "contexts": [], "sql_attempts": 0}
    for message in turn:
        if isinstance(message, ToolMessage) and message.name == "explain_schema":
            for table in tool_output(message).get("tables", []):
                result["contexts"].append(table["schema"])
                if table["source"] not in result["sources"]:
                    result["sources"].append(table["source"])
        elif isinstance(message, ToolMessage) and message.name == "run_sql":
            result["sql_attempts"] += 1
            output = tool_output(message)
            if output.get("ok"):
                result.update(sql=output["sql"], columns=output["columns"], rows=output["rows"])
        elif isinstance(message, AIMessage) and message.content:
            result["answer"] = message.content if isinstance(message.content, str) else str(message.content)
    return result


async def ask(question, db_id, thread_id, checkpointer):
    """Start the MCP server, load its tools, and ask one question."""
    client = MultiServerMCPClient(MCP_SERVERS)
    async with client.session("sql") as session:
        tools = await load_mcp_tools(session)
        return await run_agent(tools, question, db_id, thread_id, checkpointer)
