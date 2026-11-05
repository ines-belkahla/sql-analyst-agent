"""Web interface.  Run:  streamlit run app.py"""

import asyncio
import uuid

import pandas as pd
import streamlit as st
from langgraph.checkpoint.memory import InMemorySaver

from src.agent import ask
from src.config import list_databases

st.set_page_config(page_title="SQL Analyst Agent", page_icon="📊", layout="wide")

# --------------------------------------------------
# Session state
# --------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "memory" not in st.session_state:
    st.session_state.memory = InMemorySaver()  # conversation memory of the agent


def new_chat():
    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())


def show_chart(df):
    """Bar chart for category + number, line chart for year/date + number, else nothing."""
    if df.shape[1] != 2 or not pd.api.types.is_numeric_dtype(df.iloc[:, 1]) or len(df) < 2:
        return
    x = df.columns[0]
    if "year" in x.lower() or "date" in x.lower():
        st.line_chart(df, x=x, y=df.columns[1])
    else:
        st.bar_chart(df, x=x, y=df.columns[1])


def show_result(result):
    st.markdown(result["answer"])
    if result["rows"]:
        df = pd.DataFrame(result["rows"], columns=result["columns"])
        st.dataframe(df, width="stretch")
        show_chart(df)
    if result["sql"]:
        with st.expander("SQL used"):
            st.code(result["sql"], language="sql")
    if result["sources"]:
        st.caption("Sources: " + " · ".join(result["sources"]))


# --------------------------------------------------
# Sidebar
# --------------------------------------------------

with st.sidebar:
    st.title("📊 SQL Analyst")
    db_id = st.selectbox("Database", list_databases(), on_change=new_chat)
    st.button("＋ New chat", on_click=new_chat, width="stretch", type="primary")
    st.caption("The agent only runs read-only SELECT queries.")

# --------------------------------------------------
# Main area
# --------------------------------------------------

st.title("Ask a question about your data")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["content"])
        else:
            show_result(message["content"])

if question := st.chat_input("e.g. How many drivers are German?"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = asyncio.run(
                ask(question, db_id, st.session_state.thread_id, st.session_state.memory)
            )
        show_result(result)
    st.session_state.messages.append({"role": "assistant", "content": result})
