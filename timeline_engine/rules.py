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

# The only allowed anomaly_type values (spec section 4).
DUPLICATE_EVENT = "DUPLICATE_EVENT"
EVENT_ID_CONFLICT = "EVENT_ID_CONFLICT"
MISSING_ORDER_ID = "MISSING_ORDER_ID"
MISSING_EVENT_ID = "MISSING_EVENT_ID"
MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
UNKNOWN_EVENT = "UNKNOWN_EVENT"
INVALID_TRANSITION = "INVALID_TRANSITION"
ANOMALY_TYPES = frozenset(
    {
        DUPLICATE_EVENT,
        EVENT_ID_CONFLICT,
        MISSING_ORDER_ID,
        MISSING_EVENT_ID,
        MISSING_TIMESTAMP,
        INVALID_TIMESTAMP,
        UNKNOWN_EVENT,
        INVALID_TRANSITION,
    }
)

# The supplied event_type vocabulary: every state named in the business state
# machine (spec section 7). START is the implicit initial state, not an event.
VOCABULARY = frozenset(
    {
        "PLACED",
        "PAID",
        "PACKED",
        "SHIPPED",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
        "RETURN_REQUESTED",
        "RETURNED",
        "REFUNDED",
        "CANCELLED",
    }
)

# Status reported for an order with no accepted event (spec section 4).
UNKNOWN_STATUS = "UNKNOWN"
