"""Streamlit UI for Agentic SQL Search."""

import hashlib
import logging
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import streamlit as st

from agent import run_agent
from database import DB_PATH, init_db

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_CHAT_MESSAGES = 40
MAX_SCHEMA_OBJECTS = 100
MAX_SCHEMA_COLUMNS = 100

st.set_page_config(
    page_title="Agentic SQL Search",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()


def get_api_key() -> str | None:
    """Read the Gemini key locally or from Streamlit Community Cloud secrets."""
    environment_key = os.getenv("GEMINI_API_KEY", "").strip()
    if environment_key:
        return environment_key

    try:
        secret_key = str(st.secrets["GEMINI_API_KEY"]).strip()
    except (KeyError, FileNotFoundError):
        return None
    return secret_key or None


def _read_only_connection(db_path: str | Path):
    resolved_path = Path(db_path).expanduser().resolve(strict=True)
    connection = sqlite3.connect(
        f"{resolved_path.as_uri()}?mode=ro",
        uri=True,
        timeout=3,
    )
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA trusted_schema = OFF")
    return connection


def get_schema_map(db_path: str | Path) -> dict[str, list[tuple]]:
    """Return table/view column metadata without interpolating identifiers."""
    with closing(_read_only_connection(db_path)) as connection:
        objects = connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchmany(MAX_SCHEMA_OBJECTS)
        return {
            object_name: connection.execute(
                """
                SELECT cid, name, type, "notnull", dflt_value, pk
                FROM pragma_table_info(?)
                ORDER BY cid
                """,
                (object_name,),
            ).fetchmany(MAX_SCHEMA_COLUMNS)
            for (object_name,) in objects
        }


def _upload_directory() -> Path:
    """Create a temporary directory whose lifetime follows this Streamlit session."""
    if "upload_temp_dir" not in st.session_state:
        st.session_state["upload_temp_dir"] = tempfile.TemporaryDirectory(
            prefix="agentic_sql_"
        )
    return Path(st.session_state["upload_temp_dir"].name)


def save_uploaded_database(uploaded_file) -> Path:
    """Validate and store one session-scoped SQLite upload."""
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValueError("Database is larger than the 25 MB upload limit.")

    data = uploaded_file.getbuffer()
    if bytes(data[:16]) != b"SQLite format 3\x00":
        raise ValueError("The uploaded file is not a valid SQLite database.")

    digest = hashlib.sha256(data).hexdigest()
    existing_path = st.session_state.get("uploaded_db_path")
    if (
        st.session_state.get("uploaded_db_digest") == digest
        and existing_path
        and Path(existing_path).is_file()
    ):
        return Path(existing_path)

    candidate = _upload_directory() / f"{digest}.db"
    with candidate.open("wb") as database_file:
        database_file.write(data)
    candidate.chmod(0o600)

    try:
        schema = get_schema_map(candidate)
        if not schema:
            raise ValueError("The uploaded database does not contain any tables or views.")
    except (OSError, sqlite3.Error, ValueError):
        candidate.unlink(missing_ok=True)
        raise ValueError("The uploaded file is not a readable SQLite database.") from None

    if existing_path and Path(existing_path) != candidate:
        Path(existing_path).unlink(missing_ok=True)

    st.session_state["uploaded_db_path"] = str(candidate)
    st.session_state["uploaded_db_digest"] = digest
    st.session_state["uploaded_db_name"] = uploaded_file.name
    st.session_state["messages"] = []
    return candidate


def get_active_db_path() -> Path:
    return Path(st.session_state.get("active_db_path", DB_PATH))


def activate_database(db_path: str | Path) -> None:
    """Switch databases without carrying chat results across data sources."""
    new_path = str(Path(db_path))
    if st.session_state.get("active_db_path") not in (None, new_path):
        st.session_state["messages"] = []
        st.session_state.pop("pending_q", None)
    st.session_state["active_db_path"] = new_path


def render_steps(steps: list[dict]) -> None:
    with st.expander("🔎 Agent Reasoning", expanded=False):
        for index, step in enumerate(steps, 1):
            tool_name = step["tool"]
            tool_input = step["input"]
            tool_output = str(step["output"])

            st.markdown(f"**Step {index} — `{tool_name}`**")
            if tool_name == "execute_sql":
                st.code(tool_input.get("query", str(tool_input)), language="sql")
            elif tool_name == "load_skill":
                st.markdown(
                    f"Loading skill: `{tool_input.get('skill_name', str(tool_input))}`"
                )
            else:
                st.code(str(tool_input))

            preview = tool_output[:600] + (" …" if len(tool_output) > 600 else "")
            st.markdown("**Result:**")
            st.text(preview)
            if index < len(steps):
                st.divider()


api_key = get_api_key()

with st.sidebar:
    st.title("🔍 Agentic SQL Search")
    st.divider()

    st.markdown("### 🗄️ Database")
    db_mode = st.radio(
        "Choose a database",
        options=["Bundled E-Commerce Dataset", "Upload Your Own"],
        index=0,
        label_visibility="collapsed",
    )

    if db_mode == "Upload Your Own":
        uploaded_file = st.file_uploader(
            "Upload a SQLite database",
            type=["db", "sqlite", "sqlite3"],
            help="Maximum size: 25 MB. The database is opened read-only.",
            max_upload_size=25,
        )
        if uploaded_file is not None:
            try:
                active_path = save_uploaded_database(uploaded_file)
            except ValueError as error:
                st.error(str(error))
                active_path = DB_PATH
            activate_database(active_path)
            if active_path != DB_PATH:
                st.success(f"Using: {uploaded_file.name}")
        else:
            activate_database(DB_PATH)
            st.caption("Upload a database to switch from the bundled dataset.")
    else:
        activate_database(DB_PATH)
        st.caption("20 customers · 25 products · 40 orders · 5 categories")

    st.divider()
    st.markdown("### 📊 Schema")
    try:
        schema_map = get_schema_map(get_active_db_path())
    except (OSError, sqlite3.Error, ValueError):
        schema_map = {}
        st.error("The selected database could not be read.")

    if schema_map:
        for table_name, columns in schema_map.items():
            with st.expander(f"`{table_name}`"):
                for column in columns:
                    primary_key_badge = " 🔑" if column[5] else ""
                    st.markdown(f"`{column[1]}` — *{column[2]}*{primary_key_badge}")
    else:
        st.caption("No tables or views found in this database.")

    st.divider()
    if db_mode == "Bundled E-Commerce Dataset":
        st.markdown("### 💡 Try These")
        sample_questions = [
            "Who are the top 5 customers by total spend?",
            "Which product category generates the most revenue?",
            "What are the 3 best-selling products by units sold?",
            "How many orders are in each status?",
            "What is the average order value per country?",
            "List all products with less than 100 units in stock.",
            "Which customers placed more than 2 orders?",
            "What's the total revenue from Electronics?",
        ]
        for sample_question in sample_questions:
            if st.button(
                sample_question,
                use_container_width=True,
                key=f"btn_{sample_question[:20]}",
                disabled=not api_key,
            ):
                st.session_state["pending_q"] = sample_question
        st.divider()

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state["messages"] = []
        st.rerun()

    st.caption(
        "Queries, schema details, and returned rows are sent to Google Gemini to "
        "generate answers. Avoid uploading sensitive databases."
    )


st.title("🔍 Agentic SQL Search")

active_db = get_active_db_path()
if active_db == DB_PATH:
    st.markdown(
        "Ask any question about the e-commerce data in plain English. "
        "The agent writes read-only SQL, runs it, and explains the result."
    )
else:
    st.markdown(
        f"Querying **{st.session_state.get('uploaded_db_name', 'uploaded database')}** "
        "in read-only mode."
    )

if not api_key:
    st.warning(
        "Gemini is not configured yet. Add `GEMINI_API_KEY` in Streamlit "
        "**App settings → Secrets**, then reboot the app."
    )
    st.code('GEMINI_API_KEY = "your_google_ai_studio_key"', language="toml")

st.divider()

if "messages" not in st.session_state:
    st.session_state["messages"] = []

for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("steps"):
            render_steps(message["steps"])

question: str | None = st.chat_input(
    "Ask a question about the data…",
    max_chars=1_000,
    disabled=not api_key,
)
if api_key and "pending_q" in st.session_state:
    question = st.session_state.pop("pending_q")

if question and api_key:
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Querying the database…"):
            try:
                result = run_agent(question, get_active_db_path(), api_key)
                answer = result.get("answer", "No answer generated.")
                steps = result.get("steps", [])
            except Exception:
                logger.exception("Agent request failed")
                answer = (
                    "I couldn't complete that request. Check the Gemini API key and "
                    "quota, then try again with a simpler question."
                )
                steps = []

        st.markdown(answer)
        if steps:
            render_steps(steps)

    st.session_state["messages"].append(
        {"role": "assistant", "content": answer, "steps": steps}
    )
    st.session_state["messages"] = st.session_state["messages"][-MAX_CHAT_MESSAGES:]
