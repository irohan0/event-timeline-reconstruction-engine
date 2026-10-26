"""Strict event_time parsing (spec section 6 and the data dictionary).

Spec test categories: time ordering, missing/invalid values.
"""

import unittest
from datetime import datetime, timezone

from timeline_engine.timeparse import format_utc, parse_event_time

NINE_AM = datetime(2026, 4, 3, 9, 0, 0, tzinfo=timezone.utc)


class AcceptedFormatTests(unittest.TestCase):
    def test_the_three_supported_forms_are_the_same_utc_instant(self):
        for text in ("2026-04-03T09:00:00Z", "2026-04-03 09:00:00", "2026-04-03T09:00:00+00:00"):
            with self.subTest(text=text):
                self.assertEqual(parse_event_time(text), NINE_AM)

    def test_result_is_timezone_aware_utc(self):
        self.assertEqual(parse_event_time("2026-04-03 09:00:00").utcoffset().total_seconds(), 0)

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(parse_event_time("  2026-04-03T09:00:00Z \t"), NINE_AM)

    def test_calendar_edges_that_do_exist(self):
        for text, expected in (
            ("2028-02-29 00:00:00", datetime(2028, 2, 29, tzinfo=timezone.utc)),  # leap year
            ("2026-12-31T23:59:59Z", datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)),
            ("0001-01-01 00:00:00", datetime(1, 1, 1, tzinfo=timezone.utc)),
        ):
            with self.subTest(text=text):
                self.assertEqual(parse_event_time(text), expected)

    def test_mixed_forms_order_by_instant_not_by_text(self):
        # As strings, "2026-04-03 09:00:01" < "2026-04-03T09:00:00Z" (space < 'T');
        # as instants it is one second later.
        self.assertGreater(parse_event_time("2026-04-03 09:00:01"), parse_event_time("2026-04-03T09:00:00Z"))


class RejectedFormatTests(unittest.TestCase):
    def assert_invalid(self, *texts):
        for text in texts:
            with self.subTest(text=text):
                self.assertIsNone(parse_event_time(text))

    def test_empty_and_garbage(self):
        self.assert_invalid("", "   ", "not-a-date", "???", "2026", "null")

    def test_shapes_seeded_in_the_dataset(self):
        self.assert_invalid(
            "2026-04-03",  # date only
            "2026-04-03T09:00",  # missing seconds
            "2026-04-03T09:00:00.123Z",  # fractional seconds
            "2026-04-03T09:00:00z",  # lowercase z
            "2026-04-03T09:00:00+0000",  # offset without colon
            "2026-04-03T09:00:00+05:30",  # non-zero offset
            "2026/04/03 09:00:00",  # slashes
        )

    def test_mixing_parts_of_supported_forms_is_not_supported(self):
        self.assert_invalid(
            "2026-04-03T09:00:00",  # T without a zone
            "2026-04-03 09:00:00Z",  # space with Z
            "2026-04-03 09:00:00+00:00",  # space with offset
            "2026-04-03T09:00:00-00:00",  # negative zero offset
            "2026-04-03t09:00:00Z",  # lowercase t
            "2026-04-03T09:00:00 Z",  # space before Z
            "2026-04-03  09:00:00",  # double space
        )

    def test_unpadded_or_compact_numbers(self):
        self.assert_invalid("2026-4-3 09:00:00", "2026-04-03 9:00:00", "20260403T090000Z", "26-04-03 09:00:00")

    def test_impossible_dates_and_times(self):
        self.assert_invalid(
            "2026-13-42 25:61:99",
            "2026-02-30T09:00:00Z",
            "2026-02-29 00:00:00",  # 2026 is not a leap year
            "2026-04-31 00:00:00",
            "2026-00-10 00:00:00",
            "2026-04-00 00:00:00",
            "2026-04-03 24:00:00",
            "2026-04-03 23:59:60",  # leap seconds are not representable
            "0000-01-01 00:00:00",
        )

    def test_non_ascii_digits_are_rejected(self):
        # \d would match these; the spec's formats are plain ASCII digits.
        self.assert_invalid("٢٠٢٦-٠٤-٠٣ ٠٩:٠٠:٠٠", "２０２６-04-03 09:00:00")


class FormatUtcTests(unittest.TestCase):
    def test_output_format(self):
        self.assertEqual(format_utc(NINE_AM), "2026-04-03T09:00:00Z")

    def test_round_trip_from_every_supported_form(self):
        for text in ("2026-04-03T09:00:00Z", "2026-04-03 09:00:00", "2026-04-03T09:00:00+00:00"):
            with self.subTest(text=text):
                self.assertEqual(format_utc(parse_event_time(text)), "2026-04-03T09:00:00Z")

    def test_small_years_are_zero_padded(self):
        self.assertEqual(format_utc(parse_event_time("0001-01-01 00:00:00")), "0001-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
