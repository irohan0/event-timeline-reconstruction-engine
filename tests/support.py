"""Shared helpers for the test suite."""

import os
import subprocess
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(PROJECT_ROOT, "main.py")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

INPUT_HEADER = "row_id,event_id,order_id,event_type,event_time,received_at,source_system,metadata"


class TempDirTestCase(unittest.TestCase):
    """Gives each test its own scratch directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write_file(self, name, content):
        """Write ``content`` (str is UTF-8 encoded, bytes are written as-is)."""
        path = os.path.join(self.tmp, name)
        data = content.encode("utf-8") if isinstance(content, str) else content
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def write_csv(self, lines, name="input.csv"):
        """Write CSV lines (header included) with CRLF endings like the supplied data."""
        return self.write_file(name, "\r\n".join(lines) + "\r\n")


def run_cli(*args):
    """Run main.py exactly as a user would and capture the result."""
    return subprocess.run(
        [sys.executable, MAIN_PY, *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
