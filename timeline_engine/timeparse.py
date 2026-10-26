"""Strict event_time parsing and UTC formatting (spec section 6).

Exactly three representations are valid, all meaning UTC:

    2026-04-03T09:00:00Z
    2026-04-03 09:00:00
    2026-04-03T09:00:00+00:00

Anything else is invalid, even when a permissive parser would accept it:
date-only values, missing seconds, fractional seconds, lowercase "z", other
offsets ("+05:30", "+0000"), slashes, and so on. Impossible calendar values
such as 2026-02-30 or 25:61:99 are rejected too.
"""

import re
from datetime import datetime, timezone

# One pattern for the shared shape; the separator/suffix pairing is checked
# afterwards. [0-9] rather than \d, because \d also matches non-ASCII digits.
_SHAPE = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})([T ])([0-9]{2}):([0-9]{2}):([0-9]{2})(Z|\+00:00)?"
)
_ACCEPTED_FORMS = frozenset({("T", "Z"), (" ", ""), ("T", "+00:00")})


def parse_event_time(text: str) -> datetime | None:
    """Return the UTC instant for a supported event_time, or None if invalid.

    Surrounding whitespace is ignored. An empty string is also None; callers
    report it as MISSING_TIMESTAMP before trying to parse.
    """
    match = _SHAPE.fullmatch(text.strip())
    if match is None:
        return None
    year, month, day, separator, hour, minute, second, suffix = match.groups()
    if (separator, suffix or "") not in _ACCEPTED_FORMS:
        return None
    try:
        return datetime(
            int(year), int(month), int(day), int(hour), int(minute), int(second),
            tzinfo=timezone.utc,
        )
    except ValueError:  # impossible date or time, e.g. month 13 or 23:59:60
        return None


def format_utc(moment: datetime) -> str:
    """Format as YYYY-MM-DDTHH:MM:SSZ.

    Formatted field by field because strftime("%Y") does not zero-pad years
    below 1000 consistently across platforms.
    """
    moment = moment.astimezone(timezone.utc)
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}"
        f"T{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}Z"
    )
