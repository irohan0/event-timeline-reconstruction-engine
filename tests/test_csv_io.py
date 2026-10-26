"""Loading and normalizing input (spec sections 3.1 and 5) and writing reports.

Spec test category: missing/unknown values (whitespace-only cells, short rows).
"""

import csv
import os
import sys
import unittest
from unittest import mock

from tests.support import INPUT_HEADER, TempDirTestCase
from timeline_engine import rules
from timeline_engine.csv_io import EventRow, InputError, read_events, write_outputs


class NormalizationTests(TempDirTestCase):
    def load_one(self, line, header=INPUT_HEADER):
        events, _ = read_events(self.write_csv([header, line]))
        self.assertEqual(len(events), 1)
        return events[0]

    def test_trims_every_value_and_uppercases_only_event_type(self):
        row = self.load_one("  R1 , E1 ,  Ord-a ,  paid ,  2026-04-03 09:00:00  ,x,y,z")
        self.assertEqual(row, EventRow("R1", "E1", "Ord-a", "PAID", "2026-04-03 09:00:00"))

    def test_whitespace_only_cells_are_missing(self):
        row = self.load_one("R1,   ,\t, ,  ,,,")
        self.assertEqual(row, EventRow("R1", "", "", "", ""))

    def test_ids_stay_case_sensitive(self):
        row = self.load_one("R1,trcasee01,trx01,placed,2026-04-03T09:00:00Z,,,")
        self.assertEqual((row.event_id, row.order_id), ("trcasee01", "trx01"))

    def test_event_type_is_not_aliased(self):
        # Only trim + uppercase: no hyphen/underscore rewriting, no spelling fixes.
        types = [
            self.load_one(f"R1,E1,O1,{raw},2026-04-03T09:00:00Z,,,").event_type
            for raw in ("out_for_delivery", "Out-For-Delivery", "canceled", "  placed  ")
        ]
        self.assertEqual(types, ["OUT_FOR_DELIVERY", "OUT-FOR-DELIVERY", "CANCELED", "PLACED"])

    def test_unicode_look_alikes_are_not_uppercased_into_vocabulary_words(self):
        # str.upper() would turn these into SHIPPED / PAID; only ASCII letters change.
        types = [
            self.load_one(f"R1,E1,O1,{raw},2026-04-03T09:00:00Z,,,").event_type
            for raw in ("ſhipped", "paıd", "Paid")
        ]
        self.assertEqual(types, ["ſHIPPED", "PAıD", "PAID"])

    def test_event_time_is_kept_as_trimmed_text(self):
        # Parsing happens later; the duplicate check needs the raw string.
        row = self.load_one("R1,E1,O1,PAID,  2026-04-03T09:00:00+00:00  ,,,")
        self.assertEqual(row.event_time, "2026-04-03T09:00:00+00:00")


class SchemaTests(TempDirTestCase):
    def test_utf8_byte_order_mark_is_ignored(self):
        path = self.write_file(
            "bom.csv", b"\xef\xbb\xbf" + f"{INPUT_HEADER}\r\nR1,E1,O1,PAID,t,,,\r\n".encode()
        )
        events, _ = read_events(path)
        self.assertEqual(events[0].row_id, "R1")

    def test_columns_are_matched_by_name_not_position(self):
        path = self.write_csv(
            ["extra,event_time,order_id,event_type,row_id,event_id", "zzz,T,O1,paid,R1,E1"]
        )
        events, _ = read_events(path)
        self.assertEqual(events, [EventRow("R1", "E1", "O1", "PAID", "T")])

    def test_context_columns_are_optional(self):
        path = self.write_csv(["row_id,event_id,order_id,event_type,event_time", "R1,E1,O1,PAID,T"])
        events, _ = read_events(path)
        self.assertEqual(len(events), 1)

    def test_header_names_are_trimmed_and_case_insensitive(self):
        path = self.write_csv([" Row_ID ,EVENT_ID, order_id ,Event_Type,event_time", "R1,E1,O1,PAID,T"])
        events, _ = read_events(path)
        self.assertEqual(events[0].row_id, "R1")

    def test_missing_required_column_is_a_clear_error(self):
        path = self.write_csv(["row_id,event_id,order_id,event_type", "R1,E1,O1,PAID"])
        with self.assertRaisesRegex(InputError, "event_time"):
            read_events(path)

    def test_repeated_required_column_is_an_error(self):
        path = self.write_csv(["row_id,event_id,order_id,event_type,event_time,order_id", "R1,E1,O1,PAID,T,O2"])
        with self.assertRaisesRegex(InputError, "order_id"):
            read_events(path)

    def test_empty_file_is_an_error(self):
        with self.assertRaisesRegex(InputError, "empty"):
            read_events(self.write_file("empty.csv", b""))

    def test_blank_lines_before_the_header_are_skipped(self):
        events, _ = read_events(self.write_csv(["", "  ,  ", INPUT_HEADER, "R1,E1,O1,PAID,T,,,"]))
        self.assertEqual([e.row_id for e in events], ["R1"])

    def test_header_only_file_has_no_rows(self):
        events, report = read_events(self.write_csv([INPUT_HEADER]))
        self.assertEqual((events, report.rows), ([], 0))


class MalformedRowTests(TempDirTestCase):
    def test_short_rows_read_missing_cells_as_empty(self):
        events, report = read_events(self.write_csv([INPUT_HEADER, "R1,E1,O1"]))
        self.assertEqual(events, [EventRow("R1", "E1", "O1", "", "")])
        self.assertEqual(report.short_rows, 1)

    def test_long_rows_ignore_extra_cells(self):
        events, report = read_events(self.write_csv([INPUT_HEADER, "R1,E1,O1,PAID,T,a,b,c,EXTRA1,EXTRA2"]))
        self.assertEqual(events, [EventRow("R1", "E1", "O1", "PAID", "T")])
        self.assertEqual(report.long_rows, 1)

    def test_blank_lines_are_skipped_not_reported_as_records(self):
        events, report = read_events(self.write_csv([INPUT_HEADER, "", "R1,E1,O1,PAID,T,,,", "  ,  ,,,,,,", ""]))
        self.assertEqual([e.row_id for e in events], ["R1"])
        self.assertEqual(report.blank_lines_skipped, 3)

    def test_quoted_fields_may_contain_commas_and_spaces(self):
        events, _ = read_events(self.write_csv([INPUT_HEADER, 'R1,E1,O1," paid ",T,,,"a, b, c"']))
        self.assertEqual(events[0].event_type, "PAID")

    def test_invalid_utf8_bytes_do_not_crash_and_round_trip(self):
        path = self.write_file("latin1.csv", f"{INPUT_HEADER}\r\nR1,E1,O\xff1,PAID,T,,,\r\n".encode("latin-1"))
        events, _ = read_events(path)
        write_outputs(self.tmp, [], [(events[0].row_id, events[0].order_id, "E1", "X", "d")])
        with open(os.path.join(self.tmp, rules.ANOMALIES_FILENAME), "rb") as handle:
            self.assertIn(b"O\xff1", handle.read())


class WriteOutputTests(TempDirTestCase):
    def test_reports_have_exact_headers_and_crlf_endings(self):
        out_dir = os.path.join(self.tmp, "nested", "out")
        write_outputs(out_dir, [("O1", "PLACED", 1, 0, "a", "b")], [])
        with open(os.path.join(out_dir, rules.SUMMARY_FILENAME), "rb") as handle:
            self.assertEqual(
                handle.read(),
                b"order_id,final_status,valid_events,anomaly_count,"
                b"first_valid_event_time,last_valid_event_time\r\nO1,PLACED,1,0,a,b\r\n",
            )
        with open(os.path.join(out_dir, rules.ANOMALIES_FILENAME), "rb") as handle:
            self.assertEqual(handle.read(), b"row_id,order_id,event_id,anomaly_type,details\r\n")
        self.assertFalse([name for name in os.listdir(out_dir) if name.endswith(".tmp")])

    def test_failed_write_leaves_no_temp_file_and_keeps_the_previous_report(self):
        write_outputs(self.tmp, [("O1", "PLACED", 1, 0, "a", "b")], [])

        class Unwritable:
            def __str__(self):
                raise RuntimeError("simulated failure part-way through a write")

        with self.assertRaises(RuntimeError):
            write_outputs(self.tmp, [("O2", "PAID", 1, 0, "", ""), ("O3", Unwritable(), 1, 0, "", "")], [])
        self.assertEqual([name for name in os.listdir(self.tmp) if name.endswith(".tmp")], [])
        with open(os.path.join(self.tmp, rules.SUMMARY_FILENAME), "rb") as handle:
            self.assertEqual(handle.read().splitlines()[1:], [b"O1,PLACED,1,0,a,b"])


class ParserFailureTests(TempDirTestCase):
    def test_csv_parser_errors_become_input_errors_with_a_line_number(self):
        class FailingReader:
            """Returns the header, then fails the way csv.reader does on a corrupt line."""

            line_num = 2

            def __init__(self, _handle):
                self._rows = iter([INPUT_HEADER.split(",")])

            def __iter__(self):
                return self

            def __next__(self):
                row = next(self._rows, None)
                if row is None:
                    raise csv.Error("simulated parser failure")
                return row

        path = self.write_csv([INPUT_HEADER, "R1,E1,O1,PAID,T,,,"])
        with mock.patch("timeline_engine.csv_io.csv.reader", FailingReader):
            with self.assertRaisesRegex(InputError, "malformed CSV near line 2: simulated parser failure"):
                read_events(path)

    def test_nul_bytes_are_kept_or_rejected_cleanly_depending_on_python(self):
        path = self.write_file("nul.csv", f"{INPUT_HEADER}\r\nR1,E1,O1,PA\x00ID,T,,,\r\n".encode())
        if sys.version_info >= (3, 11):
            events, _ = read_events(path)
            self.assertEqual(events[0].event_type, "PA\x00ID")  # kept; later reported as UNKNOWN_EVENT
        else:  # Python 3.10's csv module cannot read NUL bytes at all
            with self.assertRaisesRegex(InputError, "malformed CSV near line 2: line contains NUL"):
                read_events(path)


if __name__ == "__main__":
    unittest.main()
