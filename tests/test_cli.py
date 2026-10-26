"""The command-line program end to end (spec sections 4, 9 and 10).

Covers the worked example (exact expected output), reproducibility under
shuffled or reformatted input, and clean failures for unusable input.
A few tests run the real `python main.py ...` in a subprocess; the rest call
main.main() in-process, which is faster and visible to coverage tools.
"""

import csv
import os
import random
import unittest

from tests.support import DATA_DIR, INPUT_HEADER, TempDirTestCase, run_cli, run_main
from timeline_engine import rules

WORKED_INPUT = os.path.join(DATA_DIR, "worked_example_input.csv")
EXPECTED_SUMMARY = os.path.join(DATA_DIR, "worked_example_summary.csv")
EXPECTED_ANOMALIES = os.path.join(DATA_DIR, "worked_example_anomalies.csv")
REPORTS = (rules.SUMMARY_FILENAME, rules.ANOMALIES_FILENAME)


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def read_bytes(paths):
    contents = []
    for path in paths:
        with open(path, "rb") as handle:
            contents.append(handle.read())
    return contents


def without_details(rows):
    return [row[:4] for row in rows]


class CliTestCase(TempDirTestCase):
    def reports(self, out_dir):
        return [os.path.join(out_dir, name) for name in REPORTS]

    def run_ok(self, input_path, out_name="out"):
        """Run in-process, assert success, return the two report paths."""
        out_dir = os.path.join(self.tmp, out_name)
        code, _, err = run_main("--input", input_path, "--output-dir", out_dir)
        self.assertEqual((code, err), (0, ""))
        return self.reports(out_dir)

    def worked_example_rows(self):
        with open(WORKED_INPUT, newline="", encoding="utf-8") as handle:
            return list(csv.reader(handle))


class WorkedExampleTests(CliTestCase):
    """The real command on the supplied example (spec section 9)."""

    def test_real_command_matches_both_expected_files(self):
        out_dir = os.path.join(self.tmp, "out")
        result = run_cli("--input", WORKED_INPUT, "--output-dir", out_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary_path, anomalies_path = self.reports(out_dir)
        self.assertEqual(read_rows(summary_path), read_rows(EXPECTED_SUMMARY))
        self.assertEqual(without_details(read_rows(anomalies_path)), without_details(read_rows(EXPECTED_ANOMALIES)))

    def test_summary_is_byte_identical_to_the_expected_file(self):
        summary_path, _ = self.run_ok(WORKED_INPUT)
        self.assertEqual(read_bytes([summary_path]), read_bytes([EXPECTED_SUMMARY]))

    def test_run_summary_is_printed(self):
        code, out, _ = run_main("--input", WORKED_INPUT, "--output-dir", os.path.join(self.tmp, "out"))
        self.assertEqual(code, 0)
        self.assertIn("Read 17 rows", out)
        self.assertIn("Orders: 7 (3 with no accepted event)", out)
        self.assertIn("Anomalies: 9", out)
        self.assertRegex(out, r"INVALID_TRANSITION\s+2")


class ReproducibilityTests(CliTestCase):
    """Deterministic output whatever the row order or file layout (spec section 10)."""

    def test_shuffled_rows_give_byte_identical_reports(self):
        header, *rows = self.worked_example_rows()
        baseline = read_bytes(self.run_ok(WORKED_INPUT, "baseline"))
        for seed in range(5):
            random.Random(seed).shuffle(rows)
            shuffled = self.write_csv([",".join(header)] + [",".join(r) for r in rows], name=f"shuffled{seed}.csv")
            with self.subTest(seed=seed):
                self.assertEqual(read_bytes(self.run_ok(shuffled, f"out{seed}")), baseline)

    def test_reformatted_file_gives_byte_identical_reports(self):
        # BOM, LF line endings, permuted columns, messy header names, no context columns.
        header, *rows = self.worked_example_rows()
        columns = ["event_time", "order_id", "row_id", "event_type", "event_id"]
        picked = [[row[header.index(c)] for c in columns] for row in reversed(rows)]
        text = "\n".join([",".join(f" {c.upper()} " for c in columns)] + [",".join(r) for r in picked]) + "\n"
        reformatted = self.write_file("reformatted.csv", b"\xef\xbb\xbf" + text.encode())
        baseline = read_bytes(self.run_ok(WORKED_INPUT, "baseline"))
        self.assertEqual(read_bytes(self.run_ok(reformatted, "reformatted")), baseline)

    def test_rerunning_overwrites_with_identical_reports(self):
        first = read_bytes(self.run_ok(WORKED_INPUT, "same"))
        self.assertEqual(read_bytes(self.run_ok(WORKED_INPUT, "same")), first)


class InputEdgeCaseTests(CliTestCase):
    def test_header_only_input_writes_header_only_reports(self):
        summary_path, anomalies_path = self.run_ok(self.write_csv([INPUT_HEADER]))
        self.assertEqual(read_rows(summary_path), [list(rules.SUMMARY_COLUMNS)])
        self.assertEqual(read_rows(anomalies_path), [list(rules.ANOMALY_COLUMNS)])

    def test_malformed_lines_are_reported_in_the_run_summary(self):
        path = self.write_csv([INPUT_HEADER, "", "R1,E1,O1", "R2,E2,O1,PAID,2026-04-03T09:00:00Z,,,,EXTRA"])
        code, out, _ = run_main("--input", path, "--output-dir", os.path.join(self.tmp, "out"))
        self.assertEqual(code, 0)
        self.assertIn("note: 1 blank line(s) skipped, 1 short row(s), 1 long row(s)", out)

    def test_repeated_row_id_is_warned_about_but_still_processed(self):
        path = self.write_csv([INPUT_HEADER, "R1,E1,O1,PLACED,2026-04-03T09:00:00Z,,,",
                               "R1,E2,O1,PAID,2026-04-03T09:05:00Z,,,"])
        code, _, err = run_main("--input", path, "--output-dir", os.path.join(self.tmp, "out"))
        self.assertEqual(code, 0)
        self.assertIn("1 row_id value(s) occur more than once", err)

    def test_empty_row_id_is_warned_about_but_still_processed(self):
        path = self.write_csv([INPUT_HEADER, ",E1,O1,PLACED,2026-04-03T09:00:00Z,,,"])
        code, _, err = run_main("--input", path, "--output-dir", os.path.join(self.tmp, "out"))
        self.assertEqual(code, 0)
        self.assertIn("1 row(s) have an empty row_id", err)


class FailureTests(CliTestCase):
    """Unusable input or output: a clear message and a nonzero exit code, never a traceback."""

    def assert_fails(self, expected_code, message, *args):
        code, _, err = run_main(*args)
        self.assertEqual(code, expected_code)
        self.assertIn(message, err)
        self.assertNotIn("Traceback", err)

    def test_missing_input_file(self):
        self.assert_fails(2, "cannot read input file", "--input", os.path.join(self.tmp, "nope.csv"),
                          "--output-dir", self.tmp)

    def test_directory_as_input(self):
        self.assert_fails(2, "is a directory", "--input", self.tmp, "--output-dir", os.path.join(self.tmp, "out"))

    def test_empty_input_file(self):
        self.assert_fails(2, "input file is empty", "--input", self.write_file("empty.csv", b""),
                          "--output-dir", self.tmp)

    def test_missing_required_column(self):
        self.assert_fails(2, "missing required column(s): event_time",
                          "--input", self.write_csv(["row_id,event_id,order_id,event_type", "R1,E1,O1,PAID"]),
                          "--output-dir", self.tmp)

    def test_output_directory_cannot_be_created(self):
        blocker = self.write_file("not_a_dir", b"")  # a file where the directory should go
        self.assert_fails(1, "cannot write reports", "--input", WORKED_INPUT, "--output-dir", blocker)

    def test_missing_input_argument_is_a_usage_error(self):
        self.assert_fails(2, "--input", "--output-dir", self.tmp)

    def test_real_command_failure_has_no_traceback(self):
        result = run_cli("--input", self.write_csv(["a,b,c", "1,2,3"]), "--output-dir", self.tmp)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing required column", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
