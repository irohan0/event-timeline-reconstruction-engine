"""The reconstruction rules, as pure functions over normalized EventRows.

Stages run in the order the spec prescribes (section 8): event-identity
checks, then single-row validation, then state transitions. Each stage
removes the rows it rejects, so every rejected row gets exactly one anomaly.
"""

from dataclasses import dataclass
from datetime import datetime

from . import rules
from .csv_io import EventRow
from .timeparse import parse_event_time


@dataclass(frozen=True, slots=True)
class Anomaly:
    """One rejected input row, as reported in anomalies.csv.

    order_id and event_id are the rejected row's own (trimmed) values.
    """

    row_id: str
    order_id: str
    event_id: str
    anomaly_type: str
    details: str

    def as_row(self) -> tuple[str, str, str, str, str]:
        return (self.row_id, self.order_id, self.event_id, self.anomaly_type, self.details)


@dataclass(frozen=True, slots=True)
class ValidEvent:
    """A row that passed every single-row check, with its parsed UTC time."""

    moment: datetime
    row: EventRow

    @property
    def sort_key(self) -> tuple[datetime, str, str]:
        # Chronological order within an order (spec section 7): parsed
        # event_time, then event_id, then row_id. Never file position.
        return (self.moment, self.row.event_id, self.row.row_id)


def resolve_event_ids(events: list[EventRow]) -> tuple[list[EventRow], list[Anomaly]]:
    """Keep one canonical row per nonempty event_id (spec section 5).

    Within each group of rows sharing an event_id, the row with the
    lexicographically smallest row_id is canonical, whatever its position in
    the file and whether or not it is itself valid. Every other row is
    compared with the canonical row (never with each other) on
    (order_id, event_type, raw event_time): equal means DUPLICATE_EVENT,
    different means EVENT_ID_CONFLICT. Rows without an event_id are never
    grouped; they pass through to validation.

    Returns the surviving rows in input order, plus one anomaly per rejected
    row (in no particular order; the report is sorted when written).
    """
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(events):
        if row.event_id:
            groups.setdefault(row.event_id, []).append(index)

    rejected: set[int] = set()
    anomalies: list[Anomaly] = []
    for indices in groups.values():
        if len(indices) == 1:
            continue
        # The trailing fields only break ties between rows that share a
        # row_id, which the spec rules out; they keep even that case
        # independent of input order.
        canonical_index, *other_indices = sorted(indices, key=lambda i: _by_row_id(events[i]))
        canonical = events[canonical_index]
        for index in other_indices:
            rejected.add(index)
            anomalies.append(_classify_repeat(events[index], canonical))

    survivors = [row for index, row in enumerate(events) if index not in rejected]
    return survivors, anomalies


def validate_rows(rows: list[EventRow]) -> tuple[list[ValidEvent], list[Anomaly]]:
    """Apply the single-row checks to canonical rows (spec section 6).

    Returns the rows eligible for timeline reconstruction (in input order)
    and one anomaly per rejected row.
    """
    valid: list[ValidEvent] = []
    anomalies: list[Anomaly] = []
    for row in rows:
        moment = parse_event_time(row.event_time) if row.event_time else None
        problem = _first_problem(row, moment)
        if problem is None:
            valid.append(ValidEvent(moment, row))
        else:
            anomalies.append(Anomaly(row.row_id, row.order_id, row.event_id, *problem))
    return valid, anomalies


def _first_problem(row: EventRow, moment: datetime | None) -> tuple[str, str] | None:
    """The first failing check in the spec's exact order, as (type, details)."""
    if not row.order_id:
        return rules.MISSING_ORDER_ID, "order_id is empty"
    if not row.event_id:
        return rules.MISSING_EVENT_ID, "event_id is empty"
    if not row.event_time:
        return rules.MISSING_TIMESTAMP, "event_time is empty"
    if moment is None:
        return (
            rules.INVALID_TIMESTAMP,
            f"event_time {row.event_time!r} is not a real date/time in a supported UTC format "
            "(YYYY-MM-DDTHH:MM:SSZ, YYYY-MM-DD HH:MM:SS or YYYY-MM-DDTHH:MM:SS+00:00)",
        )
    if row.event_type not in rules.VOCABULARY:
        shown = repr(row.event_type) if row.event_type else "empty"
        return rules.UNKNOWN_EVENT, f"event_type {shown} is not in the supported vocabulary"
    return None


def _by_row_id(row: EventRow) -> tuple[str, str, str, str]:
    return (row.row_id, row.order_id, row.event_type, row.event_time)


def _classify_repeat(row: EventRow, canonical: EventRow) -> Anomaly:
    differences = [
        f"{field} {getattr(row, field)!r} vs {getattr(canonical, field)!r}"
        for field in ("order_id", "event_type", "event_time")
        if getattr(row, field) != getattr(canonical, field)
    ]
    if differences:
        anomaly_type = rules.EVENT_ID_CONFLICT
        details = (
            f"event_id reused with a different identity than canonical row "
            f"{canonical.row_id}: {'; '.join(differences)}"
        )
    else:
        anomaly_type = rules.DUPLICATE_EVENT
        details = f"repeat of canonical row {canonical.row_id} (same order_id, event_type and event_time)"
    return Anomaly(row.row_id, row.order_id, row.event_id, anomaly_type, details)
