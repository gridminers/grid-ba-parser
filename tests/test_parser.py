import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from grid_ba_parser.parser import (
    PDFStructuredExtractor,
    ParsedPage,
    RuleBasedFormatter,
    export_to_csv,
    export_to_sqlite,
)


class _FakeVisionClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses

    def extract(self, image_bytes: bytes, page_number: int) -> str:
        _ = image_bytes
        return self._responses[page_number - 1]


class ParserTests(unittest.TestCase):
    def test_rule_based_formatter_handles_multiple_delimiters(self) -> None:
        text = """
        Invoice Number: INV-100
        Total = 4500
        Currency - USD
        Invalid line
        """
        parsed = RuleBasedFormatter().parse(text)
        self.assertEqual(parsed["Invoice Number"], "INV-100")
        self.assertEqual(parsed["Total"], "4500")
        self.assertEqual(parsed["Currency"], "USD")
        self.assertNotIn("Invalid line", parsed)

    def test_structured_extractor_and_csv_export(self) -> None:
        extractor = PDFStructuredExtractor(
            vision_client=_FakeVisionClient([
                "Account: 12345\nAmount: 200",
                "Account: 55555\nAmount: 300",
            ]),
            image_loader=lambda _path: [b"p1", b"p2"],
        )
        parsed = extractor.extract("ignored.pdf")

        self.assertEqual(
            parsed,
            [
                ParsedPage(page_number=1, fields={"Account": "12345", "Amount": "200"}),
                ParsedPage(page_number=2, fields={"Account": "55555", "Amount": "300"}),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "output.csv"
            export_to_csv(parsed, csv_path)

            with csv_path.open("r", encoding="utf-8") as fp:
                rows = list(csv.reader(fp))

            self.assertEqual(rows[0], ["page_number", "field", "value"])
            self.assertEqual(rows[1], ["1", "Account", "12345"])
            self.assertEqual(rows[-1], ["2", "Amount", "300"])


    def test_sqlite_export_rejects_unsafe_table_name(self) -> None:
        parsed = [ParsedPage(page_number=1, fields={"A": "1"})]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "parsed.db"
            with self.assertRaises(ValueError):
                export_to_sqlite(parsed, db_path, table_name="records; DROP TABLE parsed_records")


    def test_sqlite_export_handles_empty_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "parsed.db"
            export_to_sqlite([], db_path)

            connection = sqlite3.connect(str(db_path))
            try:
                row_count = connection.execute("SELECT COUNT(*) FROM parsed_records").fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(row_count, 0)

    def test_sqlite_export(self) -> None:
        parsed = [
            ParsedPage(page_number=1, fields={"A": "1", "B": "2"}),
            ParsedPage(page_number=2, fields={"C": "3"}),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "parsed.db"
            export_to_sqlite(parsed, db_path)

            connection = sqlite3.connect(str(db_path))
            try:
                rows = connection.execute(
                    "SELECT page_number, field, value FROM parsed_records ORDER BY id"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(rows, [(1, "A", "1"), (1, "B", "2"), (2, "C", "3")])


if __name__ == "__main__":
    unittest.main()
