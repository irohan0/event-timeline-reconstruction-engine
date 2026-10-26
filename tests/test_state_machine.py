"""Timeline replay and order summaries (spec sections 7 and 8)."""

import itertools
import unittest

from tests.support import make_row
from timeline_engine import rules
from timeline_engine.engine import reconstruct


def timeline(*steps, order_id="O1"):
    """Rows for one order from (event_type, "HH:MM:SS") pairs, ids in step order."""
    return [
        make_row(f"R{i:02d}", event_id=f"E{i:02d}", order_id=order_id,
                 event_type=event_type, event_time=f"2026-04-03T{clock}Z")
        for i, (event_type, clock) in enumerate(steps, start=1)
    ]


def summary_of(events, order_id="O1"):
    summaries, anomalies = reconstruct(events)
    summary = next(s for s in summaries if s.order_id == order_id)
    return summary, anomalies


class TransitionTableTests(unittest.TestCase):
    SPEC_PAIRS = {
        ("START", "PLACED"),
        ("PLACED", "PAID"), ("PLACED", "CANCELLED"),
        ("PAID", "PACKED"), ("PAID", "CANCELLED"),
        ("PACKED", "SHIPPED"), ("PACKED", "CANCELLED"),
        ("SHIPPED", "OUT_FOR_DELIVERY"),
        ("OUT_FOR_DELIVERY", "DELIVERED"),
        ("DELIVERED", "RETURN_REQUESTED"),
        ("RETURN_REQUESTED", "RETURNED"),
        ("RETURNED", "REFUNDED"),
    }

    def test_table_allows_exactly_the_spec_pairs(self):
        allowed = {
            (state, event)
            for state, event in itertools.product(rules.TRANSITIONS, rules.VOCABULARY)
            if event in rules.TRANSITIONS[state]
        }
        self.assertEqual(allowed, self.SPEC_PAIRS)

    def test_vocabulary_is_every_state_except_start(self):
        self.assertEqual(rules.VOCABULARY, frozenset(rules.TRANSITIONS) - {"START"})
        self.assertEqual(len(rules.VOCABULARY), 10)


class ReplayTests(unittest.TestCase):
    def test_full_lifecycle_through_refund(self):
        steps = ["PLACED", "PAID", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED",
                 "RETURN_REQUESTED", "RETURNED", "REFUNDED"]
        summary, anomalies = summary_of(timeline(*[(s, f"09:{i:02d}:00") for i, s in enumerate(steps)]))
        self.assertEqual((summary.final_status, summary.valid_events, anomalies), ("REFUNDED", 9, []))

    def test_invalid_transition_keeps_state_and_evaluation_continues(self):
        summary, anomalies = summary_of(timeline(("PLACED", "09:00:00"), ("SHIPPED", "09:01:00"), ("PAID", "09:02:00")))
        self.assertEqual((summary.final_status, summary.valid_events), ("PAID", 2))
        self.assertEqual([(a.row_id, a.anomaly_type) for a in anomalies], [("R02", rules.INVALID_TRANSITION)])
        self.assertIn("PLACED -> SHIPPED", anomalies[0].details)

    def test_missing_intermediate_steps_are_not_inferred(self):
        summary, anomalies = summary_of(timeline(("PLACED", "09:00:00"), ("PACKED", "09:01:00")))
        self.assertEqual((summary.final_status, summary.valid_events, len(anomalies)), ("PLACED", 1, 1))

    def test_first_event_must_be_placed(self):
        summary, anomalies = summary_of(timeline(("PAID", "09:00:00"), ("PLACED", "09:01:00")))
        self.assertEqual((summary.final_status, summary.valid_events), ("PLACED", 1))
        self.assertIn("START -> PAID", anomalies[0].details)

    def test_repeating_the_current_state_is_invalid(self):
        summary, anomalies = summary_of(timeline(("PLACED", "09:00:00"), ("PLACED", "09:01:00")))
        self.assertEqual((summary.valid_events, [a.row_id for a in anomalies]), (1, ["R02"]))

    def test_cancelled_and_refunded_are_terminal(self):
        for path in (["PLACED", "CANCELLED"],
                     ["PLACED", "PAID", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED",
                      "RETURN_REQUESTED", "RETURNED", "REFUNDED"]):
            for later in sorted(rules.VOCABULARY):
                with self.subTest(terminal=path[-1], later=later):
                    steps = [(s, f"09:{i:02d}:00") for i, s in enumerate(path + [later])]
                    summary, anomalies = summary_of(timeline(*steps))
                    self.assertEqual((summary.final_status, len(anomalies)), (path[-1], 1))

    def test_cancellation_is_allowed_only_before_shipping(self):
        for path, allowed in ((["PLACED"], True), (["PLACED", "PAID"], True), (["PLACED", "PAID", "PACKED"], True),
                              (["PLACED", "PAID", "PACKED", "SHIPPED"], False)):
            with self.subTest(after=path[-1]):
                steps = [(s, f"09:{i:02d}:00") for i, s in enumerate(path + ["CANCELLED"])]
                summary, _ = summary_of(timeline(*steps))
                self.assertEqual(summary.final_status == "CANCELLED", allowed)

    def test_valid_prefix_counts_even_if_later_events_are_invalid(self):
        summary, _ = summary_of(timeline(("PLACED", "09:00:00"), ("PAID", "09:01:00"),
                                         ("DELIVERED", "09:02:00"), ("REFUNDED", "09:03:00")))
        self.assertEqual((summary.final_status, summary.valid_events), ("PAID", 2))


class ChronologyTests(unittest.TestCase):
    def test_events_are_ordered_by_event_time_not_row_order(self):
        rows = timeline(("PLACED", "09:00:00"), ("PAID", "09:05:00"), ("PACKED", "09:20:00"))
        summary, anomalies = summary_of(list(reversed(rows)))
        self.assertEqual((summary.final_status, summary.valid_events, anomalies), ("PACKED", 3, []))

    def test_mixed_timestamp_formats_order_by_instant(self):
        rows = [
            make_row("R1", event_id="E1", event_type="PAID", event_time="2026-04-03 09:00:01"),
            make_row("R2", event_id="E2", event_type="PLACED", event_time="2026-04-03T09:00:00+00:00"),
        ]
        summary, anomalies = summary_of(rows)
        self.assertEqual((summary.final_status, summary.valid_events, anomalies), ("PAID", 2, []))

    def test_equal_times_are_ordered_by_event_id_not_row_id(self):
        # PLACED has the smaller row_id but the larger event_id, so PAID is
        # evaluated first (START -> PAID is invalid) and only PLACED is accepted.
        rows = [
            make_row("R1", event_id="TRZ1", event_type="PLACED", event_time="2026-04-03T09:00:00Z"),
            make_row("R2", event_id="TRA1", event_type="PAID", event_time="2026-04-03 09:00:00"),
        ]
        summary, anomalies = summary_of(rows)
        self.assertEqual((summary.final_status, summary.valid_events), ("PLACED", 1))
        self.assertEqual([(a.row_id, a.anomaly_type) for a in anomalies], [("R2", rules.INVALID_TRANSITION)])

    def test_first_and_last_times_are_the_accepted_extremes_in_utc(self):
        rows = timeline(("PLACED", "09:00:00"), ("SHIPPED", "09:30:00"), ("PAID", "09:10:00"))
        summary, _ = summary_of(rows)
        self.assertEqual(
            (summary.first_valid_event_time, summary.last_valid_event_time),
            ("2026-04-03T09:00:00Z", "2026-04-03T09:10:00Z"),
        )


class SummaryAccountingTests(unittest.TestCase):
    def test_order_seen_only_in_a_conflict_row_gets_an_unknown_summary(self):
        rows = [make_row("R1", order_id="O1"), make_row("R2", order_id="O2")]  # same event_id E1
        summaries, _ = reconstruct(rows)
        self.assertEqual(
            [s.as_row() for s in summaries],
            [("O1", "PLACED", 1, 0, "2026-04-03T09:00:00Z", "2026-04-03T09:00:00Z"),
             ("O2", "UNKNOWN", 0, 1, "", "")],
        )

    def test_anomaly_count_includes_every_stage(self):
        rows = [
            make_row("R1", event_id="E1"),                         # accepted PLACED
            make_row("R2", event_id="E1"),                         # DUPLICATE_EVENT
            make_row("R3", event_id="E3", event_time="bad"),       # INVALID_TIMESTAMP
            make_row("R4", event_id="E4", event_type="SHIPPED"),   # INVALID_TRANSITION
        ]
        summary, anomalies = summary_of(rows)
        self.assertEqual((summary.valid_events, summary.anomaly_count), (1, 3))
        self.assertEqual(sorted(a.anomaly_type for a in anomalies),
                         [rules.DUPLICATE_EVENT, rules.INVALID_TIMESTAMP, rules.INVALID_TRANSITION])

    def test_rows_without_order_id_are_reported_but_counted_nowhere(self):
        summaries, anomalies = reconstruct([make_row("R1", order_id="")])
        self.assertEqual((summaries, [a.anomaly_type for a in anomalies]), ([], [rules.MISSING_ORDER_ID]))

    def test_outputs_are_sorted_and_each_row_id_appears_once(self):
        rows = [
            make_row("R3", event_id="E3", order_id="b", event_type="PAID"),
            make_row("R1", event_id="E1", order_id="B"),
            make_row("R2", event_id="E1", order_id="a"),
            make_row("R10", event_id="E10", order_id="A", event_type="???"),
        ]
        summaries, anomalies = reconstruct(rows)
        self.assertEqual([s.order_id for s in summaries], ["A", "B", "a", "b"])  # code-point order
        self.assertEqual([a.row_id for a in anomalies], ["R10", "R2", "R3"])  # lexicographic


if __name__ == "__main__":
    unittest.main()
