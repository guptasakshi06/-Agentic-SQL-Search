import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import AgentConfigurationError, build_tools, run_agent
from langchain_core.messages import AIMessage, ToolMessage


class AgentToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                'CREATE TABLE "order details" (id INTEGER PRIMARY KEY, "order total" REAL)'
            )
            connection.executemany(
                'INSERT INTO "order details" ("order total") VALUES (?)',
                [(float(index),) for index in range(150)],
            )

        self.tools = {tool.name: tool for tool in build_tools(self.db_path)}

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_supports_quoted_identifiers(self):
        schema = self.tools["get_schema"].invoke({})
        self.assertIn("order details", schema)
        self.assertIn("order total", schema)

    def test_select_results_are_bounded(self):
        result = self.tools["execute_sql"].invoke(
            {
                "query": (
                    'SELECT id, "order total" FROM "order details" ORDER BY id'
                )
            }
        )
        self.assertIn("showing the first 100 rows", result)
        self.assertNotIn("150.0", result)

    def test_write_statement_is_denied(self):
        result = self.tools["execute_sql"].invoke(
            {
                "query": (
                    'WITH marker AS (SELECT 1) DELETE FROM "order details"'
                )
            }
        )
        self.assertIn("not authorized", result.lower())

        with sqlite3.connect(self.db_path) as connection:
            count = connection.execute(
                'SELECT COUNT(*) FROM "order details"'
            ).fetchone()[0]
        self.assertEqual(count, 150)

    def test_internal_database_path_is_not_queryable(self):
        result = self.tools["execute_sql"].invoke(
            {"query": "SELECT * FROM pragma_database_list"}
        )
        self.assertTrue(
            "not authorized" in result.lower() or "prohibited" in result.lower()
        )

    def test_large_generated_values_are_rejected(self):
        result = self.tools["execute_sql"].invoke(
            {"query": "SELECT length(randomblob(2000000)) AS size"}
        )
        self.assertIn("too big", result.lower())

    def test_skill_name_is_allowlisted(self):
        result = self.tools["load_skill"].invoke({"skill_name": "../README"})
        self.assertIn("only the 'sql' skill", result)

    def test_missing_key_does_not_build_the_model(self):
        previous_key = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with self.assertRaises(AgentConfigurationError):
                run_agent("Count the rows", self.db_path)
        finally:
            if previous_key is not None:
                os.environ["GEMINI_API_KEY"] = previous_key

    def test_agent_result_extracts_answer_and_tool_trace(self):
        class FakeGraph:
            def invoke(self, _input, config):
                self.config = config
                return {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "get_schema",
                                    "args": {},
                                    "id": "schema-call",
                                    "type": "tool_call",
                                }
                            ],
                        ),
                        ToolMessage(
                            content="TABLE: order details",
                            tool_call_id="schema-call",
                        ),
                        AIMessage(content="There are 150 rows."),
                    ]
                }

        fake_graph = FakeGraph()
        with (
            patch("agent._get_llm", return_value=object()),
            patch("agent.create_agent", return_value=fake_graph),
        ):
            result = run_agent(
                "How many rows are there?",
                self.db_path,
                api_key="test-key",
            )

        self.assertEqual(result["answer"], "There are 150 rows.")
        self.assertEqual(result["steps"][0]["tool"], "get_schema")
        self.assertEqual(result["steps"][0]["output"], "TABLE: order details")
        self.assertEqual(fake_graph.config["recursion_limit"], 12)


if __name__ == "__main__":
    unittest.main()
