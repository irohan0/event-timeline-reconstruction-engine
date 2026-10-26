"""Constants taken verbatim from the assessment specification.

Everything the engine treats as "the rules" lives here as plain data, so the
logic modules never hard-code a column name or label.
"""

# Input columns the engine needs (spec section 5). The context-only columns
# received_at, source_system and metadata are accepted but never read, so a
# file without them is still valid input.
ROW_ID = "row_id"
EVENT_ID = "event_id"
ORDER_ID = "order_id"
EVENT_TYPE = "event_type"
EVENT_TIME = "event_time"
REQUIRED_COLUMNS = (ROW_ID, EVENT_ID, ORDER_ID, EVENT_TYPE, EVENT_TIME)

# Output files and their exact column order (spec section 4).
SUMMARY_FILENAME = "order_summary.csv"
ANOMALIES_FILENAME = "anomalies.csv"
SUMMARY_COLUMNS = (
    "order_id",
    "final_status",
    "valid_events",
    "anomaly_count",
    "first_valid_event_time",
    "last_valid_event_time",
)
ANOMALY_COLUMNS = ("row_id", "order_id", "event_id", "anomaly_type", "details")

# The only allowed anomaly_type values (spec section 4), in the spec's order.
DUPLICATE_EVENT = "DUPLICATE_EVENT"
EVENT_ID_CONFLICT = "EVENT_ID_CONFLICT"
MISSING_ORDER_ID = "MISSING_ORDER_ID"
MISSING_EVENT_ID = "MISSING_EVENT_ID"
MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
UNKNOWN_EVENT = "UNKNOWN_EVENT"
INVALID_TRANSITION = "INVALID_TRANSITION"
ANOMALY_TYPES = (
    DUPLICATE_EVENT,
    EVENT_ID_CONFLICT,
    MISSING_ORDER_ID,
    MISSING_EVENT_ID,
    MISSING_TIMESTAMP,
    INVALID_TIMESTAMP,
    UNKNOWN_EVENT,
    INVALID_TRANSITION,
)

# Business state machine (spec section 7): current state -> the only event
# types that may follow it. No state may repeat itself, and CANCELLED and
# REFUNDED are terminal.
START_STATE = "START"
TRANSITIONS = {
    START_STATE: frozenset({"PLACED"}),
    "PLACED": frozenset({"PAID", "CANCELLED"}),
    "PAID": frozenset({"PACKED", "CANCELLED"}),
    "PACKED": frozenset({"SHIPPED", "CANCELLED"}),
    "SHIPPED": frozenset({"OUT_FOR_DELIVERY"}),
    "OUT_FOR_DELIVERY": frozenset({"DELIVERED"}),
    "DELIVERED": frozenset({"RETURN_REQUESTED"}),
    "RETURN_REQUESTED": frozenset({"RETURNED"}),
    "RETURNED": frozenset({"REFUNDED"}),
    "CANCELLED": frozenset(),
    "REFUNDED": frozenset(),
}

# The supplied event_type vocabulary: every state in the table above.
# START is the implicit initial state, not an event, so it is excluded.
VOCABULARY = frozenset(TRANSITIONS) - {START_STATE}

# Status reported for an order with no accepted event (spec section 4).
UNKNOWN_STATUS = "UNKNOWN"
