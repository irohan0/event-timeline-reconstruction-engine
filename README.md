# Event timeline reconstruction engine

A command-line tool that rebuilds each order's timeline from a messy e-commerce event log and reports every row it had to reject. It follows the rules in the assessment brief (cited below as §N) and uses only the Python standard library.

Results for the full dataset are summarized in [ANALYSIS.md](ANALYSIS.md).

## Setup and usage

You need Python 3.10 or newer. There is nothing to install.

```bash
python main.py --input data/order_events.csv --output-dir output
```

This writes `output/order_summary.csv` and `output/anomalies.csv` and prints a short run summary:

```
Read 181,775 rows from data/order_events.csv
Orders: 30,840 (405 with no accepted event)
Accepted events: 139,647
Anomalies: 42,128
  DUPLICATE_EVENT         9,675
  EVENT_ID_CONFLICT       3,717
  MISSING_ORDER_ID        1,567
  MISSING_EVENT_ID        2,397
  MISSING_TIMESTAMP       3,066
  INVALID_TIMESTAMP       2,969
  UNKNOWN_EVENT           5,338
  INVALID_TRANSITION     13,399
Wrote output/order_summary.csv and output/anomalies.csv in 2.25s
```

Any other CSV with the same columns works without changes. `--output-dir` defaults to `output` and is created if needed.

Exit codes: `0` success, `2` the input can't be used (file missing, required column missing, empty file), `1` the reports couldn't be written. Errors are short messages on stderr, never tracebacks.

The reports generated from the full dataset are committed in `output/`. The large input CSVs are not, as the brief asks; copy `order_events.csv` into `data/` to regenerate them. The small worked-example files are included because the tests use them.

## Running the tests

```bash
python -m unittest        # standard library only
python -m pytest          # same tests, if you have pytest installed
```

There are 103 tests and they take about two seconds. The five categories the brief asks for (§11) are covered here:

| Category | Where |
|---|---|
| Duplicates | `tests/test_identity.py`, plus a property test that removing reported duplicates changes only anomaly counts |
| Time ordering | `ChronologyTests` in `tests/test_state_machine.py`, `tests/test_timeparse.py` |
| Invalid transitions | `ReplayTests` and `TransitionTableTests` in `tests/test_state_machine.py` |
| Missing/unknown values | `tests/test_validation.py`, `tests/test_csv_io.py` |
| Deterministic ties, reproducibility | tie-break tests in `tests/test_state_machine.py`; shuffled and reformatted input in `tests/test_cli.py` and `tests/test_properties.py` |

`tests/test_cli.py` also runs the real command on the worked example and checks both reports against the expected files. `tests/test_properties.py` generates 30 seeded random datasets mixing every kind of problem and checks rules that must hold for any input: each row is accepted or reported exactly once, accepted events always form a legal path, and output never depends on row order.

## Project layout

```
main.py                  CLI: arguments, exit codes, run summary
timeline_engine/
  rules.py               constants from the brief: columns, anomaly types, transitions
  timeparse.py           strict event_time parsing and UTC formatting
  csv_io.py              reading and normalizing input, writing reports
  engine.py              the pipeline: identity checks, validation, replay, summaries
tests/                   unittest suite (also runs under pytest)
output/                  reports for the full dataset
ANALYSIS.md              one-page analysis of the full run
```

## How it works

The stages run in the order §8 prescribes. Each one removes the rows it rejects, so a row gets at most one anomaly and every input row ends up either accepted or in `anomalies.csv`.

1. **Load and normalize** (§5). Columns are found by header name. Every cell is trimmed and an empty cell means missing. `event_type` is uppercased. `received_at`, `source_system` and `metadata` are never loaded, so they can't affect any decision.
2. **Event identity** (§5). Rows that share a non-empty `event_id` form a group, and the lexicographically smallest `row_id` is the canonical row. Every other row in the group is compared with the canonical row on `(order_id, event_type, raw event_time)`: equal means `DUPLICATE_EVENT`, different means `EVENT_ID_CONFLICT`. Rows without an `event_id` are never grouped.
3. **Validation** (§6). Canonical rows are checked in the brief's order (order_id, event_id, empty time, unparseable time, unknown type) and only the first failure is reported. Rows that pass carry their parsed UTC time forward.
4. **Replay** (§7). Eligible rows are grouped by `order_id`, sorted by `(event_time, event_id, row_id)` and run through the transition table from `START`. A disallowed event becomes `INVALID_TRANSITION` and leaves the state where it was. Missing steps are never filled in.
5. **Reports** (§4, §8). There is one summary row for every non-empty `order_id` that appears anywhere in the input, including orders that only appear in rejected rows (those are `UNKNOWN`). `anomaly_count` is the number of anomaly rows carrying that `order_id`. Summaries are sorted by `order_id` and anomalies by `row_id`.

Each stage is a pure function from rows to rows, which is what makes them easy to test on their own.

## Design decisions

Where the brief leaves room for interpretation, this is what I chose. Every point below has a test.

- **Timestamps are strict.** Only `2026-04-03T09:00:00Z`, `2026-04-03 09:00:00` and `2026-04-03T09:00:00+00:00` are valid. Mixing their parts (a `T` with no zone, a space followed by `Z`) is rejected, and so are lowercase `z`, `+0000`, other offsets, fractional seconds, missing seconds, date-only values and impossible dates such as `2026-02-30` or `25:61:99`. The data dictionary warns that permissive parsers accept too much, so the parser first matches the exact shape and only then builds a `datetime`, which rejects impossible values. Digits must be ASCII, because Python's `\d` also matches Arabic and full-width digits.
- **Identity compares the raw time text**, as §5 says. `2026-01-10T00:00:00Z` and `2026-01-10 00:00:00` are the same instant but not the same text, so a reused `event_id` with those two values is a conflict, not a duplicate.
- **The smallest `row_id` is canonical even when it's the broken row.** If the canonical row says `not-a-date` and a later copy has a valid time, the canonical row is reported as `INVALID_TIMESTAMP` and the copy as `EVENT_ID_CONFLICT`.
- **"Lexicographic" means plain string comparison** (Unicode code point order), so `R10` sorts before `R9`. The same ordering is used for `order_id` and for the `event_id` tie-break.
- **`event_type` is uppercased for ASCII letters only.** Python's `str.upper()` turns some non-ASCII look-alikes into ASCII words (`ſhipped` becomes `SHIPPED`, `paıd` becomes `PAID`), which would quietly invent aliases that §5 forbids. An empty `event_type` is `UNKNOWN_EVENT`.
- **An anomaly belongs to the rejected row's own `order_id`.** A conflict row that names a different order counts toward that order, which gets a summary row even if it appears nowhere else.
- **Input is matched by column name.** Header names are trimmed and lowercased, so column order and stray spaces don't matter. Only the five columns the rules use are required; the context columns are optional and extra columns are ignored. A missing required column stops the run with exit code 2.
- **Malformed rows don't stop the run.** Blank lines are skipped. A short row reads its missing cells as empty, and extra cells on a long row are ignored; both are counted in the run summary. Bytes that aren't valid UTF-8 pass through unchanged (Python's `surrogateescape`) rather than being replaced.
- **Broken `row_id` guarantees produce a warning.** The brief says `row_id` is unique and never empty. If a file breaks that, the run continues with a warning on stderr and ties are broken on the remaining fields, so the output is still deterministic.
- **`details` is free text** (§4). `INVALID_TRANSITION` details start with the same wording as the worked example, for example `CANCELLED -> DELIVERED is not allowed`, followed by the event time.
- **Reports are UTF-8 with CRLF line endings.** That's the `csv` module's default and matches the supplied expected files, so the worked-example summary comes out byte-identical. Each report is written to a temporary file and then renamed, so an interrupted run never leaves half a report behind. `.gitattributes` stops Git from rewriting those line endings.

## Complexity

With n input rows, time is O(n log n) and memory is O(n). Grouping by `event_id` and by `order_id` is linear; sorting within groups and sorting the final reports dominates. The whole file is held in memory as small frozen dataclasses.

On the full dataset (181,775 rows), a run takes 2 to 4 seconds end to end on my Windows laptop and peaks at about 126 MB of memory.

## How I checked the results

On top of the unit tests:

- The worked-example summary is byte-identical to `worked_example_summary.csv`, and the anomalies match `worked_example_anomalies.csv` in every column except `details`.
- Before writing the Python code, I profiled the data in PowerShell/.NET, and later recomputed every stage there as an independent check. Every count matches, for example 9,675 duplicates, 3,717 conflicts and 139,647 accepted transitions.
- A second implementation, written from the brief alone with a different parser and different algorithms, produces identical reports on the worked example, the debug subset and the full dataset.
- Reversed, shuffled and reformatted copies of the full input produce byte-identical reports. The reformatted copies had permuted columns, LF line endings, a byte-order mark, or only the required columns.
- The output is identical on Python 3.10.11 and 3.12.10, and the test suite passes on both.
- The tests give 100% line and branch coverage of `timeline_engine`. I also planted 27 realistic bugs one at a time (a `row_id` tie-break, keeping the first copy in the file, `str.upper()`, and others), and each was caught by at least one test.

These checks were one-off development scripts and aren't part of the submission.

## Limitations

- Everything is held in memory. That's fine at this size (about 126 MB), but a file much larger than RAM would need an external sort or partitioning by `order_id` and `event_id`.
- Only comma-separated UTF-8 input is handled. There is no delimiter or encoding detection.
- Python 3.10's `csv` module refuses NUL bytes, so on 3.10 such a file stops with `malformed CSV near line N: line contains NUL` (exit code 2). Python 3.11 and later read the file and handle the row normally. The supplied data has no NUL bytes.
- Only UTC timestamps in the three listed forms are accepted. That's deliberate: accepting real offsets such as `+05:30` would need a change to the rules themselves.
- The `details` column is English text meant for people, not machines.

## Tools and AI disclosure

The program uses the Python standard library only (`csv`, `datetime`, `re`, `argparse`, `dataclasses`), so there is no `requirements.txt`. During development I also used `pytest` as an optional test runner and `coverage` to measure test coverage; neither is needed to run the program or the tests.

I used Claude Code, Anthropic's AI coding assistant, while building this: to help draft code, tests and documentation, and to build the cross-checks listed above. I reviewed the results of every stage and can explain each decision in this README.
