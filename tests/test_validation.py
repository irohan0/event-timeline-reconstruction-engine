"""Single-row validation and its precedence (spec section 6).

Spec test category: missing/unknown values.
"""

import unittest
from datetime import datetime, timezone

from tests.support import make_row
from timeline_engine import rules
from timeline_engine.engine import resolve_event_ids, validate_rows


def verdict(row):
    """The anomaly type for one row, or "ELIGIBLE"."""
    valid, anomalies = validate_rows([row])
    return anomalies[0].anomaly_type if anomalies else "ELIGIBLE"


class SingleProblemTests(unittest.TestCase):
    def test_each_problem_maps_to_its_anomaly_type(self):
        cases = {
            rules.MISSING_ORDER_ID: make_row("R1", order_id=""),
            rules.MISSING_EVENT_ID: make_row("R1", event_id=""),
            rules.MISSING_TIMESTAMP: make_row("R1", event_time=""),
            rules.INVALID_TIMESTAMP: make_row("R1", event_time="2026-02-30T09:00:00Z"),
            rules.UNKNOWN_EVENT: make_row("R1", event_type="HANDOFF"),
        }
        for expected, row in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(verdict(row), expected)

    def test_every_vocabulary_type_is_eligible(self):
        for event_type in sorted(rules.VOCABULARY):
            with self.subTest(event_type=event_type):
                self.assertEqual(verdict(make_row("R1", event_type=event_type)), "ELIGIBLE")

    def test_empty_event_type_is_unknown(self):
        self.assertEqual(verdict(make_row("R1", event_type="")), rules.UNKNOWN_EVENT)

    def test_near_miss_and_alias_types_are_unknown(self):
        # No aliases are invented: only exact vocabulary entries are accepted.
        for event_type in ("CANCELED", "OUT-FOR-DELIVERY", "OUTFORDELIVERY", "START", "UNKNOWN", "PLACED_", "???",
                           "ſHIPPED", "PAıD"):
            with self.subTest(event_type=event_type):
                self.assertEqual(verdict(make_row("R1", event_type=event_type)), rules.UNKNOWN_EVENT)


class PrecedenceTests(unittest.TestCase):
    """Only the first applicable error is reported, in the spec's order."""

    def test_precedence_order(self):
        cases = [
            (rules.MISSING_ORDER_ID, dict(order_id="", event_id="", event_time="", event_type="???")),
            (rules.MISSING_EVENT_ID, dict(event_id="", event_time="", event_type="???")),
            (rules.MISSING_EVENT_ID, dict(event_id="", event_time="not-a-date")),
            (rules.MISSING_TIMESTAMP, dict(event_time="", event_type="???")),
            (rules.INVALID_TIMESTAMP, dict(event_time="not-a-date", event_type="???")),
        ]
        for expected, fields in cases:
            with self.subTest(fields=fields):
                self.assertEqual(verdict(make_row("R1", **fields)), expected)

    def test_one_anomaly_per_rejected_row(self):
        rows = [make_row("R1", order_id="", event_id="", event_time=""), make_row("R2", event_type="???")]
        valid, anomalies = validate_rows(rows)
        self.assertEqual((valid, [a.row_id for a in anomalies]), ([], ["R1", "R2"]))

    def test_identity_checks_run_before_validation(self):
        # R2 repeats R1's event_id with an empty order_id: it is an
        # EVENT_ID_CONFLICT, never re-reported as MISSING_ORDER_ID.
        survivors, identity = resolve_event_ids([make_row("R1"), make_row("R2", order_id="")])
        valid, validation = validate_rows(survivors)
        self.assertEqual([(a.row_id, a.anomaly_type) for a in identity], [("R2", rules.EVENT_ID_CONFLICT)])
        self.assertEqual((len(valid), validation), (1, []))


class EligibleRowTests(unittest.TestCase):
    def test_eligible_rows_carry_the_parsed_utc_time(self):
        rows = [
            make_row("R1", event_id="A", event_time="2026-04-03T09:00:00Z"),
            make_row("R2", event_id="B", event_time="2026-04-03 09:00:00"),
            make_row("R3", event_id="C", event_time="2026-04-03T09:00:00+00:00"),
        ]
        valid, _ = validate_rows(rows)
        nine_am = datetime(2026, 4, 3, 9, tzinfo=timezone.utc)
        self.assertEqual([(v.row.row_id, v.moment) for v in valid], [("R1", nine_am), ("R2", nine_am), ("R3", nine_am)])

    def test_sort_key_is_time_then_event_id_then_row_id(self):
        valid, _ = validate_rows([make_row("R9", event_id="E2"), make_row("R1", event_id="E1")])
        self.assertEqual(sorted(v.sort_key for v in valid)[0][1:], ("E1", "R1"))

    def test_anomaly_keeps_the_rows_own_ids(self):
        _, anomalies = validate_rows([make_row("R1", order_id="", event_id="E7"), make_row("R2", order_id="O5", event_id="")])
        self.assertEqual(
            [(a.row_id, a.order_id, a.event_id) for a in anomalies],
            [("R1", "", "E7"), ("R2", "O5", "")],
        )


if __name__ == "__main__":
    unittest.main()
