"""Command-line entry point.

    python main.py --input data/order_events.csv --output-dir output

Exit codes: 0 success, 2 unusable input (missing file, bad schema), 1 the
reports could not be written.
"""

import argparse
import os
import sys
import time
from collections import Counter

from timeline_engine import rules
from timeline_engine.csv_io import InputError, read_events, write_outputs
from timeline_engine.engine import reconstruct


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconstruct order timelines from an event CSV and report anomalies."
    )
    parser.add_argument("--input", required=True, help="path to the input event CSV")
    parser.add_argument(
        "--output-dir",
        default="output",
        help="directory for order_summary.csv and anomalies.csv (default: output)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()

    if os.path.isdir(args.input):
        print(f"error: {args.input}: is a directory, expected a CSV file", file=sys.stderr)
        return 2
    try:
        events, load_report = read_events(args.input)
    except InputError as exc:
        print(f"error: {args.input}: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot read input file: {exc}", file=sys.stderr)
        return 2

    warn_about_row_ids(events)
    summaries, anomalies = reconstruct(events)

    try:
        summary_path, anomalies_path = write_outputs(
            args.output_dir,
            [summary.as_row() for summary in summaries],
            [anomaly.as_row() for anomaly in anomalies],
        )
    except OSError as exc:
        print(f"error: cannot write reports: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - started
    print(f"Read {load_report.rows:,} rows from {args.input}")
    if load_report.blank_lines_skipped or load_report.short_rows or load_report.long_rows:
        print(
            f"  note: {load_report.blank_lines_skipped} blank line(s) skipped, "
            f"{load_report.short_rows} short row(s), {load_report.long_rows} long row(s)"
        )
    unknown = sum(1 for s in summaries if s.final_status == rules.UNKNOWN_STATUS)
    print(f"Orders: {len(summaries):,} ({unknown:,} with no accepted event)")
    print(f"Accepted events: {sum(s.valid_events for s in summaries):,}")
    print(f"Anomalies: {len(anomalies):,}")
    by_type = Counter(a.anomaly_type for a in anomalies)
    for anomaly_type in rules.ANOMALY_TYPES:
        print(f"  {anomaly_type:<20} {by_type[anomaly_type]:>8,}")
    print(f"Wrote {summary_path} and {anomalies_path} in {elapsed:.2f}s")
    return 0


def warn_about_row_ids(events) -> None:
    """The spec promises unique, nonempty row_ids; say so if a file breaks that."""
    counts = Counter(row.row_id for row in events)
    empty = counts.pop("", 0)
    repeated = sum(1 for n in counts.values() if n > 1)
    if empty:
        print(f"warning: {empty} row(s) have an empty row_id", file=sys.stderr)
    if repeated:
        print(
            f"warning: {repeated} row_id value(s) occur more than once; "
            "row_id is expected to be unique",
            file=sys.stderr,
        )


if __name__ == "__main__":
    sys.exit(main())
