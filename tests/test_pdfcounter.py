import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import PDFCounter


class TestPDFCounterCLI(unittest.TestCase):
    def test_run_cli_without_argument_returns_usage_exit_code(self):
        with patch("sys.argv", ["PDFCounter.py"]):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = PDFCounter.run_cli()

        output = buffer.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("Usage: python PDFCounter.py file.pdf", output)

    def test_run_cli_missing_file_returns_error_exit_code(self):
        with patch("sys.argv", ["PDFCounter.py", "/tmp/does-not-exist.pdf"]):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = PDFCounter.run_cli()

        output = buffer.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("Error: File does not exist", output)


class TestInputValidation(unittest.TestCase):
    def test_count_pdf_pages_rejects_non_pdf_extension(self):
        with self.assertRaises(ValueError):
            PDFCounter.count_pdf_pages("README.md")


if __name__ == "__main__":
    unittest.main()
