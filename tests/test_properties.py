"""Properties that must hold for any input, checked on seeded random messy data.

Spec test categories: reproducibility (shuffled input), duplicates, invalid
transitions and anomaly accounting, all at once.
"""

import random
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone

from timeline_engine import rules
from timeline_engine.csv_io import EventRow
from timeline_engine.engine import reconstruct
from timeline_engine.timeparse import format_utc, parse_event_time

SEEDS = range(30)
HAPPY_PATH = ["PLACED", "PAID", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED",
              "RETURN_REQUESTED", "RETURNED", "REFUNDED"]
NOISE_TYPES = ["CANCELLED", "???", "HANDOFF", "", "START"]
FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S+00:00")
BAD_TIMES = ["", "not-a-date", "2026-02-30T09:00:00Z", "2026-04-03T09:00:00z", "2026-04-03", "2026-04-03T09:00"]
BASE = datetime(2026, 4, 3, 9, tzinfo=timezone.utc)


def messy_dataset(seed, orders=25):
    """Orders with out-of-order, tied, skipped, unknown and malformed events,
    plus duplicated and conflicting repeats of existing event_ids.

    row_ids are "R1", "R2", ... so lexicographic order differs from creation
    order ("R10" < "R9"), which exercises the canonical-row rule.
    """
    rng = random.Random(seed)
    rows: list[EventRow] = []

    def add(event_id, order_id, event_type, event_time):
        rows.append(EventRow(f"R{len(rows) + 1}", event_id, order_id, event_type, event_time))

    order_ids = [rng.choice([f"O{n}", f"o{n}"]) for n in range(orders)]  # case twins are distinct orders
    for n, order_id in enumerate(order_ids):
        minute = rng.randrange(0, 60)
        path = HAPPY_PATH[: rng.randrange(1, len(HAPPY_PATH) + 1)]
        if rng.random() < 0.3:
            path.insert(rng.randrange(1, len(path) + 1), "CANCELLED")
        for step, event_type in enumerate(path):
            if rng.random() < 0.15:
                event_type = rng.choice(NOISE_TYPES + HAPPY_PATH)
            minute += rng.choice([0, 0, 1, 5, 30])  # equal timestamps are common
            if rng.random() < 0.1:
                minute -= rng.randrange(1, 90)  # arrives "late" in time order
            text = (BASE + timedelta(minutes=minute)).strftime(rng.choice(FORMATS))
            if rng.random() < 0.08:
                text = rng.choice(BAD_TIMES)
            event_id = "" if rng.random() < 0.04 else f"E{n}-{step}"
            add(event_id, "" if rng.random() < 0.03 else order_id, event_type, text)

    originals = [r for r in rows if r.event_id]
    for _ in range(len(rows) // 4):
        src = rng.choice(originals)
        roll = rng.random()
        if roll < 0.5:  # exact repeat
            add(src.event_id, src.order_id, src.event_type, src.event_time)
        elif roll < 0.7:  # reused for another order
            add(src.event_id, rng.choice(order_ids), src.event_type, src.event_time)
        elif roll < 0.85:  # reused with another type
            add(src.event_id, src.order_id, rng.choice(HAPPY_PATH), src.event_time)
        else:  # same instant, other text format (or a bad time)
            moment = parse_event_time(src.event_time)
            text = moment.strftime(rng.choice(FORMATS)) if moment else rng.choice(BAD_TIMES)
            add(src.event_id, src.order_id, src.event_type, text)
    return rows


def as_rows(result):
    summaries, anomalies = result
    return [s.as_row() for s in summaries], [a.as_row() for a in anomalies]


class PropertyTests(unittest.TestCase):
    def test_generator_produces_every_kind_of_anomaly(self):
        # Guards the other properties against a generator too tame to matter.
        seen = Counter()
        for seed in SEEDS:
            _, anomalies = reconstruct(messy_dataset(seed))
            seen.update(a.anomaly_type for a in anomalies)
        self.assertEqual(set(seen), set(rules.ANOMALY_TYPES))

    def test_every_row_is_accepted_or_reported_exactly_once(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rows = messy_dataset(seed)
                summaries, anomalies = reconstruct(rows)
                row_ids = [a.row_id for a in anomalies]
                self.assertEqual(len(row_ids), len(set(row_ids)))
                self.assertEqual(row_ids, sorted(row_ids))
                self.assertEqual(sum(s.valid_events for s in summaries) + len(anomalies), len(rows))

    def test_summaries_are_complete_and_consistent(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rows = messy_dataset(seed)
                summaries, anomalies = reconstruct(rows)
                order_ids = [s.order_id for s in summaries]
                self.assertEqual(order_ids, sorted({r.order_id for r in rows if r.order_id}))
                per_order = Counter(a.order_id for a in anomalies)
                for s in summaries:
                    self.assertEqual(s.anomaly_count, per_order[s.order_id])
                    unknown = s.final_status == rules.UNKNOWN_STATUS
                    self.assertEqual(unknown, s.valid_events == 0)
                    self.assertEqual(unknown, s.first_valid_event_time == "" == s.last_valid_event_time)

    def test_accepted_events_form_a_legal_path_matching_the_summary(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rows = messy_dataset(seed)
                summaries, anomalies = reconstruct(rows)
                rejected = {a.row_id for a in anomalies}
                accepted: dict[str, list[EventRow]] = {}
                for row in rows:
                    if row.row_id not in rejected:
                        accepted.setdefault(row.order_id, []).append(row)
                for s in summaries:
                    events = sorted(accepted.get(s.order_id, []),
                                    key=lambda r: (parse_event_time(r.event_time), r.event_id, r.row_id))
                    state = rules.START_STATE
                    for event in events:
                        self.assertIn(event.event_type, rules.TRANSITIONS[state])
                        state = event.event_type
                    if events:
                        self.assertEqual(s.final_status, state)
                        self.assertEqual(s.first_valid_event_time, format_utc(parse_event_time(events[0].event_time)))
                        self.assertEqual(s.last_valid_event_time, format_utc(parse_event_time(events[-1].event_time)))

    def test_output_does_not_depend_on_row_order(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rows = messy_dataset(seed)
                expected = as_rows(reconstruct(rows))
                shuffler = random.Random(seed)
                for _ in range(5):
                    shuffler.shuffle(rows)
                    self.assertEqual(as_rows(reconstruct(rows)), expected)

    def test_dropping_reported_duplicates_changes_only_their_anomaly_counts(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rows = messy_dataset(seed)
                summaries, anomalies = reconstruct(rows)
                duplicates = {a.row_id: a.order_id for a in anomalies if a.anomaly_type == rules.DUPLICATE_EVENT}
                trimmed_summaries, trimmed_anomalies = reconstruct([r for r in rows if r.row_id not in duplicates])
                removed = Counter(duplicates.values())
                expected = [(s.order_id, s.final_status, s.valid_events, s.anomaly_count - removed[s.order_id],
                             s.first_valid_event_time, s.last_valid_event_time) for s in summaries]
                self.assertEqual([s.as_row() for s in trimmed_summaries], expected)
                self.assertEqual([a.as_row() for a in trimmed_anomalies],
                                 [a.as_row() for a in anomalies if a.row_id not in duplicates])


if __name__ == "__main__":
    unittest.main()
