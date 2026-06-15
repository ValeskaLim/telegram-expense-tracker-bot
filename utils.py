"""Parsing and formatting helpers for the Expense Tracker bot."""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Optional

from constant import BANKS, MAX_AMOUNT, MIN_AMOUNT, MONTH_NAMES_ID, MONTHS

# ─────────────────────────────────────────────────────────────────────────────
# Time zone aware "now"
# ─────────────────────────────────────────────────────────────────────────────
# Expenses are logged against the user's local date (Asia/Jakarta / WIB), not
# the server's. This keeps "today" — and the 23:00 WIB daily report — correct
# even when the VPS runs in another timezone.
try:
    from zoneinfo import ZoneInfo

    _TZ = ZoneInfo("Asia/Jakarta")
except Exception:  # pragma: no cover - no tzdata: use a fixed WIB (UTC+7) offset
    _TZ = timezone(timedelta(hours=7))

# Public handle for scheduling (e.g. JobQueue.run_daily). Always a real tzinfo.
JAKARTA_TZ = _TZ


def now() -> datetime:
    """Current time in Asia/Jakarta (falls back to server local time)."""
    return datetime.now(_TZ)


def today() -> datetime:
    """Today's date at midnight (naive), in Asia/Jakarta."""
    n = now()
    return datetime(n.year, n.month, n.day)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────
def parse_month(token: str) -> Optional[int]:
    """Return the month number for an Indonesian/English name, or None."""
    return MONTHS.get(token.strip().lower())


def make_date(day: int, month: Optional[int], year: int) -> Optional[datetime]:
    """Build a datetime, returning None for impossible dates (e.g. 31 Feb)."""
    if not month:
        return None
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def parse_date_parts(parts: list[str]) -> Optional[datetime]:
    """Parse ['16', 'Desember', '2026'] into a datetime, or None."""
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        year = int(parts[2])
    except ValueError:
        return None
    return make_date(day, parse_month(parts[1]), year)


def parse_day_month(day_str: str, month_str: str, year: int) -> Optional[datetime]:
    """Parse a day + month name for a known year (used by /add)."""
    try:
        day = int(day_str)
    except ValueError:
        return None
    return make_date(day, parse_month(month_str), year)


def parse_amount(token: str) -> Optional[int]:
    """Parse an amount, tolerating thousands separators ('16.000', '16,000').

    Returns the integer amount if valid and within limits, otherwise None.
    """
    cleaned = token.replace(".", "").replace(",", "").replace("_", "").strip()
    if not cleaned.isdigit():
        return None
    amount = int(cleaned)
    if amount < MIN_AMOUNT or amount > MAX_AMOUNT:
        return None
    return amount


def normalize_bank(token: str) -> Optional[str]:
    """Return the canonical bank name if valid, else None."""
    bank = token.strip().lower()
    return bank if bank in BANKS else None


# ─────────────────────────────────────────────────────────────────────────────
# Formatting
# ─────────────────────────────────────────────────────────────────────────────
def format_rupiah(amount: int) -> str:
    """Format an integer as Indonesian Rupiah, e.g. 16000 -> 'Rp 16.000'."""
    return f"Rp {amount:,}".replace(",", ".")


def format_date_id(date: datetime) -> str:
    """Format a date in Indonesian, e.g. '16 Desember 2026'."""
    return f"{date.day} {MONTH_NAMES_ID[date.month]} {date.year}"


def esc(value: object) -> str:
    """HTML-escape any value so user text can't break message formatting."""
    return html.escape(str(value))


def banks_help() -> str:
    """Comma-separated list of valid banks for help/error messages."""
    return ", ".join(f"<code>{b}</code>" for b in BANKS)


# ─────────────────────────────────────────────────────────────────────────────
# Command argument parsing
# ─────────────────────────────────────────────────────────────────────────────
class InputError(Exception):
    """A user-facing input error. Its message is HTML ready to send."""


def parse_add_args(
    args: list[str], *, year: int, default_date: datetime
) -> tuple[datetime, str, int, str]:
    """Parse /add arguments into (date, notes, amount, bank).

    Two accepted forms (the last token is always the bank, second-to-last the
    amount, everything before is the note — optionally prefixed by day + month):

        /add <notes...> <amount> <bank>                -> default_date
        /add <day> <month> <notes...> <amount> <bank>  -> that date, `year`

    Raises InputError (with a ready-to-send HTML message) on invalid input.
    """
    if len(args) < 3:
        raise InputError("Invalid format.")

    bank = normalize_bank(args[-1])
    if bank is None:
        raise InputError(
            f"Invalid bank <code>{esc(args[-1])}</code>. Choose one of: {banks_help()}."
        )

    amount = parse_amount(args[-2])
    if amount is None:
        raise InputError(
            f"Invalid amount <code>{esc(args[-2])}</code>. "
            f"Use a whole number between {MIN_AMOUNT} and {MAX_AMOUNT:,}.".replace(",", ".")
        )

    middle = args[:-2]
    looks_dated = (
        len(middle) >= 2 and middle[0].isdigit() and parse_month(middle[1]) is not None
    )
    if looks_dated:
        if len(middle) < 3:
            raise InputError(
                "Please add a note after the date, e.g. "
                "<code>/add 16 Desember Makan siang 20000 bca1</code>."
            )
        date = parse_day_month(middle[0], middle[1], year)
        if date is None:
            raise InputError(f"Invalid date <code>{esc(middle[0] + ' ' + middle[1])}</code>.")
        notes = " ".join(middle[2:]).strip()
    else:
        date = default_date
        notes = " ".join(middle).strip()

    if not notes:
        raise InputError("Please include a note describing the expense.")

    return date, notes, amount, bank
