"""Shared helpers for the test suite."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

import main
from timeline_engine.csv_io import EventRow

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(PROJECT_ROOT, "main.py")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

INPUT_HEADER = "row_id,event_id,order_id,event_type,event_time,received_at,source_system,metadata"


def make_row(row_id, event_id="E1", order_id="O1", event_type="PLACED", event_time="2026-04-03T09:00:00Z"):
    """Build an already-normalized EventRow; tests override only what matters."""
    return EventRow(row_id, event_id, order_id, event_type, event_time)


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


def run_main(*args):
    """Call main.main() in-process; returns (exit_code, stdout, stderr).

    Faster than a subprocess and visible to coverage tools. argparse usage
    errors raise SystemExit, which is turned into its exit code.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main.main(list(args))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def run_cli(*args):
    """Run main.py exactly as a user would and capture the result."""
    return subprocess.run(
        [sys.executable, MAIN_PY, *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
