# 🔍 Agentic SQL Search

> Ask a question in plain English and this agent inspects the schema, writes the SQL, runs it, and returns a clear answer.

![Agentic SQL Search Demo](assets/demo.png)

## Overview

A natural language to SQL agent that lets you query an e-commerce SQLite database in plain English, no SQL knowledge required. 

Instead of hardcoding SQL, the agent follows a deliberate three-step process before answering: it loads a SQL skill document for syntax rules and query patterns, inspects the live database schema to confirm column names, then writes and executes the appropriate query. The Streamlit UI exposes the full reasoning trace so you can see every tool call and its result.

## Features

- **Natural Language Queries:** Ask questions in plain English and the agent figures out the SQL
- **Skill-Based Reasoning:** Agent loads a SQL skill document before writing queries, reducing syntax errors and hallucinations
- **Schema Inspection:** Agent always checks the live schema before querying, never guesses column names
- **Full Reasoning Trace:** Every tool call, query, and result is visible in the UI's Agent Reasoning expander
- **Bundled Dataset:** Ships with a ready-to-use e-commerce SQLite database, no external setup required
- **Bring Your Own Database:** Upload a SQLite database up to 25 MB; each session gets an isolated, read-only temporary copy
- **Sample Questions:** Sidebar includes 8 pre-built questions to get started immediately

## Tech Stack

**Frameworks & Libraries:**
- [LangChain](https://python.langchain.com/): Agent orchestration via `create_agent`, tool definitions, and LLM integration
- [LangGraph](https://langchain-ai.github.io/langgraph/): Agent execution runtime used by LangChain
- [Streamlit](https://streamlit.io/): Interactive web UI with chat interface

**Models (via Google AI / Gemini API):**
- **LLM:** [`gemma-4-26b-a4b-it`](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)

**Database:**
- SQLite (bundled sample dataset, auto-generated on first run)

## Dataset

The bundled e-commerce database includes:

| Table | Description |
|---|---|
| `customers` | 20 customers across 10 countries |
| `products` | 25 products across 5 categories |
| `orders` | 40 orders with statuses: pending, processing, shipped, delivered, cancelled |
| `order_items` | 78 line items linking orders to products |

Categories: Electronics, Clothing, Books, Home & Garden, Sports

## How It Works

```
User Question
      │
      ▼
  load_skill('sql')       ← loads syntax rules + query patterns
      │
      ▼
  get_schema()            ← inspects live table/column structure
      │
      ▼
  execute_sql(query)      ← runs the generated SELECT query
      │
      ▼
  Answer + Reasoning Trace
```

**Tools:**
- **`load_skill`**: reads the allowlisted `skills/sql.md` guide with SQLite syntax, safety rules, and efficient query patterns
- **`get_schema`**: queries `sqlite_master` and `PRAGMA table_info` to return the live database structure
- **`execute_sql`**: runs any SELECT query and returns a formatted table (SELECT-only for safety)

## Prerequisites

- Python 3.12
- A Google AI Studio API key

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/guptasakshi06/-Agentic-SQL-Search agentic-sql-search
cd agentic-sql-search
```

### 2. Set Up Environment Variables

```bash
cp .env.example .env
```

Open `.env` and add your key:

```env
GEMINI_API_KEY=your_google_ai_studio_key_here
```

Get your API key at [Google AI Studio](https://aistudio.google.com/app/apikey).

### 3. Create an Environment and Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Usage

```bash
streamlit run app.py
```

Navigate to `http://localhost:8501` in your browser.

The bundled e-commerce SQLite database is created automatically on first run. No extra setup needed.

To query your own database, select **Upload Your Own** in the sidebar and upload any `.db`, `.sqlite`, or `.sqlite3` file. The agent will inspect the schema automatically and you can start asking questions right away.

> Uploaded databases are kept in a session-scoped temporary directory and opened read-only. Schema details, generated queries, and returned rows are sent to Google Gemini to produce the answer, so do not upload sensitive data.

## Deploy on Streamlit Community Cloud

1. In Streamlit Community Cloud, create a new app from this repository.
2. Select branch **`main`** and entrypoint **`app.py`**.
3. In **Advanced settings**, choose **Python 3.12**.
4. Add this secret:

```toml
GEMINI_API_KEY = "your_google_ai_studio_key_here"
```

5. Deploy the app. No external database or system package is required.

If the app is public, monitor or restrict Gemini API usage because visitors consume the API quota associated with this key.

## Tests

```bash
python -m unittest discover -v
```

**Example questions to try (bundled dataset):**
- "Who are the top 5 customers by total spend?"
- "Which product category generates the most revenue?"
- "What is the average order value per country?"
- "Which customers placed more than 2 orders?"

## Project Structure

```text
agentic_sql_search/
├── app.py              # Streamlit UI and chat interface
├── agent.py            # LangGraph ReAct agent and tool definitions
├── database.py         # SQLite schema and sample data seeder
├── skills/
│   └── sql.md          # SQL syntax rules and query patterns loaded by the agent
├── tests/
│   ├── __init__.py
│   ├── test_agent.py   # Read-only SQL, isolation, and result-limit tests
│   └── test_database.py # Concurrent database initialization test
├── assets/
│   └── demo.png        # App screenshot
├── data/
│   └── ecommerce.db    # SQLite database (auto-generated, gitignored)
├── .env.example        # API key template
├── requirements.txt   # Pinned deployment dependencies
└── README.md
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

[⬆ Back to Top](#-agentic-sql-search)
