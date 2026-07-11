import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import database


class DatabaseInitializationTests(unittest.TestCase):
    def test_concurrent_initialization_seeds_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "ecommerce.db"
            with patch("database.DB_PATH", database_path):
                with ThreadPoolExecutor(max_workers=4) as executor:
                    list(executor.map(lambda _: database.init_db(), range(4)))

            with sqlite3.connect(database_path) as connection:
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in ("customers", "products", "orders", "order_items")
                }
                foreign_key_errors = connection.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()

            self.assertEqual(
                counts,
                {
                    "customers": 20,
                    "products": 25,
                    "orders": 40,
                    "order_items": 78,
                },
            )
            self.assertEqual(foreign_key_errors, [])


if __name__ == "__main__":
    unittest.main()
