# Analysis of the full run

Results of `python main.py --input data/order_events.csv --output-dir output`.

## Counts

| Events | Count | Orders | Count |
|---|---:|---|---:|
| Input rows | 181,775 | All orders | 30,840 |
| Accepted transitions | 139,647 | With at least one anomaly | 23,721 |
| Rejected rows (anomalies) | 42,128 | With no accepted event (`UNKNOWN`) | 405 |

Every row is accounted for once (139,647 accepted + 42,128 rejected = 181,775). Anomalies by type: `INVALID_TRANSITION` 13,399, `DUPLICATE_EVENT` 9,675, `UNKNOWN_EVENT` 5,338, `EVENT_ID_CONFLICT` 3,717, `MISSING_TIMESTAMP` 3,066, `INVALID_TIMESTAMP` 2,969, `MISSING_EVENT_ID` 2,397, `MISSING_ORDER_ID` 1,567. Those last 1,567 rows have no order to count toward, so `anomaly_count` sums to 40,561.

Final statuses: `DELIVERED` 7,956, `CANCELLED` 5,725, `REFUNDED` 3,289, `SHIPPED` 3,261, `PACKED` 3,258, `PAID` 2,916, `PLACED` 1,990, `RETURN_REQUESTED` 1,163, `RETURNED` 877, `UNKNOWN` 405.

## Edge cases

**Ties decided by event ID.** In 60 orders a `PAID` and a `PLACED` event share an instant, written in two formats. Ties sort by `event_id` and the `PAID` event's ID comes first, so `START -> PAID` is rejected and only `PLACED` is accepted. Breaking the tie by `row_id` or file position would wrongly accept both.

**The canonical copy can be the broken one.** Of 13,019 reused event IDs, 6,599 have their smallest `row_id` somewhere other than first in the file, so "keep the first copy" fails about half the time. In 75 groups the canonical row has `not-a-date` and a later copy is valid; the canonical row still wins (`INVALID_TIMESTAMP`) and the copy is an `EVENT_ID_CONFLICT`. In 75 more, both copies hold the same instant in different formats, which is also a conflict because the brief compares raw text.

**Timestamps that look valid.** The file plants 904 rows of `2026-13-42 25:61:99`, 927 slash-separated dates, 18 rows of `2026-02-30`, and 19 rows each of `+05:30`, `+0000`, lowercase `z`, fractional seconds, missing seconds and date-only values. Python 3.12's `datetime.fromisoformat` accepts five of those shapes; the engine rejects all of them.

## Engineering tradeoff

I used the standard `csv` module and plain in-memory Python objects instead of pandas. By default `pandas.read_csv` turns strings like `NA` and `null` into NaN and keeps surrounding whitespace, but the identity and opaque-ID rules need each cell as an exact string. Plain strings keep those rules visible, and a full run still takes only 2 to 4 seconds and about 126 MB. The cost is memory: a file much larger than RAM would need an external sort on `event_id` and `order_id`, which I judged unnecessary for a 21 MB input.
