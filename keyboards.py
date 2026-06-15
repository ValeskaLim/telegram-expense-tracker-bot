"""Reply-keyboard builders for the button-driven UI.

These are ``ReplyKeyboardMarkup`` panels that "pop up" attached to the text
input. Tapping a button sends its label as a normal message, which the matching
conversation state (see flows.py) interprets. Typed steps (notes/nominal/ID)
use a panel with only a Cancel button plus an ``input_field_placeholder`` so the
field being entered is clearly named inside the input box.
"""
from __future__ import annotations

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

from constant import BANKS, MONTH_NAMES_ID
from utils import now

# ─────────────────────────────────────────────────────────────────────────────
# Button labels (flows.py imports these to interpret taps)
# ─────────────────────────────────────────────────────────────────────────────
CANCEL = "❌ Cancel"
TODAY = "📅 Today"
THIS_MONTH = "📅 This month"
ALL_BANKS = "🏦 All banks"
SUBMIT = "✅ Submit"
CONFIRM_DELETE = "🗑️ Confirm delete"

MENU_ADD = "➕ Add"
MENU_CHECK = "📅 Check"
MENU_AUDIT = "📊 Audit"
MENU_CHANGE = "✏️ Change"
MENU_DELETE = "🗑️ Delete"
MENU_HELP = "❓ Help"
MENU_REPORT = "🔔 Daily report"

# Field picker labels -> internal field key (Change flow)
FIELD_LABELS = {
    "💰 Amount": "amount",
    "📝 Notes": "notes",
    "🏦 Bank": "bank",
    "📅 Date": "date",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _chunk(items: list[str], per_row: int) -> list[list[str]]:
    return [items[i : i + per_row] for i in range(0, len(items), per_row)]


def _kb(rows: list[list[str]], placeholder: str, one_time: bool = True) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=one_time,
        input_field_placeholder=placeholder,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────────────────────────────
def main_menu_kb() -> ReplyKeyboardMarkup:
    return _kb(
        [
            [MENU_ADD, MENU_CHECK],
            [MENU_AUDIT, MENU_CHANGE],
            [MENU_DELETE, MENU_HELP],
            [MENU_REPORT],
        ],
        "Tap an action…",
        one_time=False,
    )


def day_kb(today: bool = True) -> ReplyKeyboardMarkup:
    rows: list[list[str]] = []
    if today:
        rows.append([TODAY])
    rows += _chunk([str(d) for d in range(1, 32)], 7)
    rows.append([CANCEL])
    return _kb(rows, "Tap a day 1–31…")


def month_kb(today: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[str]] = []
    if today:
        rows.append([THIS_MONTH])
    rows += _chunk([MONTH_NAMES_ID[m][:3] for m in range(1, 13)], 3)
    rows.append([CANCEL])
    return _kb(rows, "Tap a month…")


def year_kb() -> ReplyKeyboardMarkup:
    y = now().year
    return _kb([[str(y), str(y - 1), str(y - 2)], [CANCEL]], "Tap a year…")


def bank_kb(include_all: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[str]] = []
    if include_all:
        rows.append([ALL_BANKS])
    rows += _chunk(list(BANKS), 2)
    rows.append([CANCEL])
    return _kb(rows, "Tap a bank…")


def field_kb() -> ReplyKeyboardMarkup:
    return _kb(
        [["💰 Amount", "📝 Notes"], ["🏦 Bank", "📅 Date"], [CANCEL]],
        "Tap a field…",
    )


def confirm_kb(action: str = "submit") -> ReplyKeyboardMarkup:
    label = SUBMIT if action == "submit" else CONFIRM_DELETE
    return _kb([[label], [CANCEL]], "Confirm…")


def text_kb(placeholder: str) -> ReplyKeyboardMarkup:
    """A typed step: only Cancel, with the field named in the input box."""
    return _kb([[CANCEL]], placeholder, one_time=False)


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
