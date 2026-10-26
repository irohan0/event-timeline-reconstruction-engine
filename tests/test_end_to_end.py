"""The real CLI on the supplied worked example (spec section 9)."""

import csv
import os
import random
import unittest

from tests.support import DATA_DIR, TempDirTestCase, run_cli
from timeline_engine import rules

WORKED_INPUT = os.path.join(DATA_DIR, "worked_example_input.csv")
EXPECTED_SUMMARY = os.path.join(DATA_DIR, "worked_example_summary.csv")
EXPECTED_ANOMALIES = os.path.join(DATA_DIR, "worked_example_anomalies.csv")


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


class WorkedExampleTests(TempDirTestCase):
    def run_on(self, input_path):
        out_dir = os.path.join(self.tmp, "out")
        result = run_cli("--input", input_path, "--output-dir", out_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        return os.path.join(out_dir, rules.SUMMARY_FILENAME), os.path.join(out_dir, rules.ANOMALIES_FILENAME)

    def test_summary_matches_expected_file_exactly(self):
        summary_path, _ = self.run_on(WORKED_INPUT)
        self.assertEqual(read_rows(summary_path), read_rows(EXPECTED_SUMMARY))

    def test_anomalies_match_expected_file_ignoring_details(self):
        _, anomalies_path = self.run_on(WORKED_INPUT)
        self.assertEqual(without_details(read_rows(anomalies_path)), without_details(read_rows(EXPECTED_ANOMALIES)))

    def test_shuffled_input_gives_byte_identical_reports(self):
        with open(WORKED_INPUT, newline="", encoding="utf-8") as handle:
            header, *rows = list(csv.reader(handle))
        baseline = read_bytes(self.run_on(WORKED_INPUT))
        for seed in range(5):
            random.Random(seed).shuffle(rows)
            shuffled = self.write_csv([",".join(header)] + [",".join(r) for r in rows], name=f"shuffled{seed}.csv")
            with self.subTest(seed=seed):
                self.assertEqual(read_bytes(self.run_on(shuffled)), baseline)


if __name__ == "__main__":
    unittest.main()
