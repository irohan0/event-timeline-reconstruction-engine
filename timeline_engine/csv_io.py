"""Reading the input CSV and writing the two output reports.

This module is the only place that touches files. It turns raw CSV text into
normalized EventRow records (spec section 5) and writes already-computed rows
back out; it makes no business decisions.
"""

import contextlib
import csv
import os
import string
from dataclasses import dataclass

from . import rules

# A UTF-8 byte-order mark, if present, is dropped transparently.
INPUT_ENCODING = "utf-8-sig"
OUTPUT_ENCODING = "utf-8"
# Bytes that are not valid UTF-8 are carried through as surrogate escapes and
# written back out unchanged: we neither crash nor invent replacement text.
ENCODING_ERRORS = "surrogateescape"

# The csv module rejects fields over 128 KiB by default. Real fields are tiny,
# but one stray quote can swallow a long stretch of the file; we would rather
# load it than abort. 2**31 - 1 fits a C long on every platform.
csv.field_size_limit(2**31 - 1)

# event_type is upper-cased for ASCII letters only. Full Unicode upper()
# maps look-alikes onto vocabulary words ("ſhipped" -> "SHIPPED",
# "paıd" -> "PAID"), which would invent aliases the spec forbids.
_ASCII_UPPER = str.maketrans(string.ascii_lowercase, string.ascii_uppercase)


class InputError(ValueError):
    """The input file cannot be read with the specified schema."""


@dataclass(frozen=True, slots=True)
class EventRow:
    """One input record after normalization.

    Every value is stripped of surrounding whitespace, and an empty string
    means "missing". event_type is also upper-cased (ASCII letters only, so
    no aliases are invented). event_time stays as the trimmed text because
    the duplicate check compares the raw string; it is parsed later.
    Context-only columns (received_at, source_system, metadata) are
    deliberately not kept: they must not influence any decision.
    """

    row_id: str
    event_id: str
    order_id: str
    event_type: str
    event_time: str


@dataclass
class LoadReport:
    """Facts about the physical file, reported to the user after a run."""

    rows: int = 0
    blank_lines_skipped: int = 0
    short_rows: int = 0  # fewer cells than the header; missing cells read as empty
    long_rows: int = 0  # more cells than the header; extra cells ignored


def read_events(path: str) -> tuple[list[EventRow], LoadReport]:
    """Load and normalize every record of the CSV at ``path``."""
    report = LoadReport()
    events: list[EventRow] = []
    with open(path, newline="", encoding=INPUT_ENCODING, errors=ENCODING_ERRORS) as handle:
        reader = csv.reader(handle)
        try:
            header = next((cells for cells in reader if any(cell.strip() for cell in cells)), None)
            if header is None:
                raise InputError("input file is empty (no header row)")
            row_id_at, event_id_at, order_id_at, type_at, time_at = _locate_columns(header)
            width = len(header)

            for cells in reader:
                if not any(cell.strip() for cell in cells):
                    report.blank_lines_skipped += 1
                    continue
                if len(cells) < width:
                    report.short_rows += 1
                    cells = cells + [""] * (width - len(cells))
                elif len(cells) > width:
                    report.long_rows += 1
                events.append(
                    EventRow(
                        row_id=cells[row_id_at].strip(),
                        event_id=cells[event_id_at].strip(),
                        order_id=cells[order_id_at].strip(),
                        event_type=cells[type_at].strip().translate(_ASCII_UPPER),
                        event_time=cells[time_at].strip(),
                    )
                )
        except csv.Error as exc:
            raise InputError(f"malformed CSV near line {reader.line_num}: {exc}") from None

    report.rows = len(events)
    return events, report


def _locate_columns(header: list[str]) -> tuple[int, ...]:
    """Return the cell index of each required column, matched by name.

    Header names are compared after trimming and lower-casing, so column
    order, stray spaces and extra columns do not matter.
    """
    positions: dict[str, list[int]] = {}
    for index, name in enumerate(header):
        positions.setdefault(name.strip().lower(), []).append(index)

    missing = [name for name in rules.REQUIRED_COLUMNS if name not in positions]
    if missing:
        raise InputError(
            f"missing required column(s): {', '.join(missing)}; "
            f"expected at least: {', '.join(rules.REQUIRED_COLUMNS)}"
        )
    repeated = [name for name in rules.REQUIRED_COLUMNS if len(positions[name]) > 1]
    if repeated:
        raise InputError(f"required column(s) appear more than once: {', '.join(repeated)}")
    return tuple(positions[name][0] for name in rules.REQUIRED_COLUMNS)


def write_outputs(output_dir: str, summary_rows, anomaly_rows) -> tuple[str, str]:
    """Write both reports into ``output_dir`` (created if needed).

    Rows must already be sorted and ordered like the output columns. Returns
    the two file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    summary_path = os.path.join(output_dir, rules.SUMMARY_FILENAME)
    anomalies_path = os.path.join(output_dir, rules.ANOMALIES_FILENAME)
    _write_csv(summary_path, rules.SUMMARY_COLUMNS, summary_rows)
    _write_csv(anomalies_path, rules.ANOMALY_COLUMNS, anomaly_rows)
    return summary_path, anomalies_path


def _write_csv(path: str, columns, rows) -> None:
    # Write to a temporary file first so an interrupted run never leaves a
    # half-written report behind under the real name; if writing fails, the
    # temporary file is removed and any previous report stays as it was.
    temp_path = path + ".tmp"
    try:
        with open(temp_path, "w", newline="", encoding=OUTPUT_ENCODING, errors=ENCODING_ERRORS) as handle:
            writer = csv.writer(handle)  # default dialect: minimal quoting, CRLF line endings
            writer.writerow(columns)
            writer.writerows(rows)
        os.replace(temp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(temp_path)
        raise
