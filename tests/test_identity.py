"""Duplicate and conflicting event IDs (spec section 5)."""

import random
import unittest

from tests.support import INPUT_HEADER, TempDirTestCase, make_row
from timeline_engine import rules
from timeline_engine.csv_io import read_events
from timeline_engine.engine import resolve_event_ids


def outcome(events):
    """(surviving row_ids, {rejected row_id: anomaly_type}) for compact asserts."""
    survivors, anomalies = resolve_event_ids(events)
    return [row.row_id for row in survivors], {a.row_id: a.anomaly_type for a in anomalies}


class DuplicateVersusConflictTests(unittest.TestCase):
    def test_exact_repeat_is_a_duplicate(self):
        self.assertEqual(
            outcome([make_row("R1"), make_row("R2")]),
            (["R1"], {"R2": rules.DUPLICATE_EVENT}),
        )

    def test_any_differing_identity_field_is_a_conflict(self):
        for field, value in (("order_id", "O2"), ("event_type", "PAID"), ("event_time", "2026-04-03T09:05:00Z")):
            with self.subTest(field=field):
                other = make_row("R2", **{field: value})
                self.assertEqual(outcome([make_row("R1"), other]), (["R1"], {"R2": rules.EVENT_ID_CONFLICT}))

    def test_same_instant_in_another_format_is_a_conflict(self):
        # The spec compares the raw (trimmed) event_time text, not the parsed instant.
        other = make_row("R2", event_time="2026-04-03 09:00:00")
        self.assertEqual(outcome([make_row("R1"), other]), (["R1"], {"R2": rules.EVENT_ID_CONFLICT}))

    def test_every_repeat_is_compared_with_the_canonical_row_only(self):
        # R2 and R3 match each other but not the canonical R1: both are conflicts.
        events = [make_row("R1"), make_row("R2", event_type="PAID"), make_row("R3", event_type="PAID")]
        self.assertEqual(
            outcome(events),
            (["R1"], {"R2": rules.EVENT_ID_CONFLICT, "R3": rules.EVENT_ID_CONFLICT}),
        )

    def test_conflict_is_attributed_to_the_rows_own_order(self):
        _, anomalies = resolve_event_ids([make_row("R1"), make_row("R2", order_id="O2")])
        self.assertEqual(
            [(a.row_id, a.order_id, a.event_id) for a in anomalies],
            [("R2", "O2", "E1")],
        )


class CanonicalRowTests(unittest.TestCase):
    def test_smallest_row_id_wins_not_file_position(self):
        events = [make_row("R2", event_type="PAID"), make_row("R1")]
        self.assertEqual(outcome(events), (["R1"], {"R2": rules.EVENT_ID_CONFLICT}))

    def test_row_id_order_is_lexicographic_not_numeric(self):
        events = [make_row("R9"), make_row("R10", event_type="PAID")]
        self.assertEqual(outcome(events), (["R10"], {"R9": rules.EVENT_ID_CONFLICT}))

    def test_canonical_row_wins_even_when_it_is_invalid(self):
        # Validity is judged later; here the bad-timestamp row is still canonical.
        events = [make_row("R1", event_time="not-a-date"), make_row("R2")]
        self.assertEqual(outcome(events), (["R1"], {"R2": rules.EVENT_ID_CONFLICT}))

    def test_result_is_independent_of_input_order(self):
        events = [
            make_row("R5", event_id="A"),
            make_row("R3", event_id="A", event_type="PAID"),
            make_row("R4", event_id="A", event_type="PAID"),
            make_row("R1", event_id="B", order_id="O2"),
            make_row("R2", event_id="B", order_id="O2"),
            make_row("R6", event_id=""),
        ]
        expected_survivors, expected_anomalies = outcome(events)
        rng = random.Random(7)
        for _ in range(25):
            shuffled = events[:]
            rng.shuffle(shuffled)
            survivors, anomalies = outcome(shuffled)
            self.assertEqual(sorted(survivors), sorted(expected_survivors))
            self.assertEqual(anomalies, expected_anomalies)
        self.assertEqual(sorted(expected_survivors), ["R1", "R3", "R6"])


class GroupingTests(unittest.TestCase):
    def test_rows_without_event_id_are_never_grouped(self):
        events = [make_row("R1", event_id=""), make_row("R2", event_id="")]
        self.assertEqual(outcome(events), (["R1", "R2"], {}))

    def test_event_ids_are_case_sensitive(self):
        events = [make_row("R1", event_id="TRCaseE1"), make_row("R2", event_id="trcasee1")]
        self.assertEqual(outcome(events), (["R1", "R2"], {}))

    def test_survivors_keep_input_order(self):
        events = [make_row("R3", event_id=""), make_row("R2", event_id="X"), make_row("R1", event_id="")]
        self.assertEqual(outcome(events), (["R3", "R2", "R1"], {}))


class NormalizationInteractionTests(TempDirTestCase):
    """Identity is compared after trimming and event_type upper-casing."""

    def resolve_csv(self, *lines):
        events, _ = read_events(self.write_csv([INPUT_HEADER, *lines]))
        return outcome(events)

    def test_padding_and_case_of_event_type_still_make_a_duplicate(self):
        self.assertEqual(
            self.resolve_csv(
                "R1,E1,O1,PAID,2026-04-03T09:00:00Z,,,",
                "R2,  E1  ,  O1 ,  paid ,  2026-04-03T09:00:00Z  ,,,",
            ),
            (["R1"], {"R2": rules.DUPLICATE_EVENT}),
        )

    def test_context_columns_never_affect_identity(self):
        # received_at / source_system / metadata differ, yet this is a duplicate.
        self.assertEqual(
            self.resolve_csv(
                "R1,E1,O1,PAID,2026-04-03T09:00:00Z,2026-04-03T10:00:00Z,WEB,a",
                "R2,E1,O1,PAID,2026-04-03T09:00:00Z,2026-05-01T00:00:00Z,COURIER,b",
            ),
            (["R1"], {"R2": rules.DUPLICATE_EVENT}),
        )


if __name__ == "__main__":
    unittest.main()
