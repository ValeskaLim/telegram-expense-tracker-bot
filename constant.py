"""Shared constants for the Expense Tracker bot."""

# ─────────────────────────────────────────────────────────────────────────────
# Banks / payment sources
# ─────────────────────────────────────────────────────────────────────────────
# The `bank` field of every expense must be one of these values. Add new ones
# here and they are accepted everywhere automatically.
BANKS = ("bca1", "bca2", "mandiri", "cimb")

# ─────────────────────────────────────────────────────────────────────────────
# Amount limits (in Rupiah)
# ─────────────────────────────────────────────────────────────────────────────
MIN_AMOUNT = 1
MAX_AMOUNT = 1_000_000_000  # 1 billion

# ─────────────────────────────────────────────────────────────────────────────
# Month names → month number
# ─────────────────────────────────────────────────────────────────────────────
# Accepts Indonesian and English, full names and common abbreviations, so the
# user can type "Desember", "December", or "Des" interchangeably.
MONTHS = {
    # Indonesian (full)
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11,
    "desember": 12,
    # English (full)
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "august": 8, "october": 10, "december": 12,
    # Abbreviations (Indonesian + English, only the unambiguous ones)
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "agu": 8,
    "aug": 8, "agt": 8, "sep": 9, "sept": 9, "okt": 10, "oct": 10, "nov": 11,
    "des": 12, "dec": 12,
}

# Month number → Indonesian month name, used for display so all output is in
# Indonesian regardless of how the user typed the month.
MONTH_NAMES_ID = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
    7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November",
    12: "Desember",
}
