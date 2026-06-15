"""Inline keyboard builders for the button-driven UI.

Pure functions, no Telegram I/O. A tap is routed by the active conversation
*state* (see flows.py), not by callback prefix, so the same keyboard (e.g. the
day grid) is reused across the Add / Check / Change flows.

Callback-data scheme:
    menu:<add|check|audit|change|delete|help|home>
    day:<1-31> | day:today
    mon:<1-12> | mon:today
    yr:<YYYY>
    bank:<name> | bank:all
    fld:<amount|notes|bank|date>
    ok:<submit|delete>
    cancel
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from constant import BANKS, MONTH_NAMES_ID
from utils import now

CANCEL = "cancel"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _rows(buttons: list[InlineKeyboardButton], per_row: int) -> list[list[InlineKeyboardButton]]:
    """Chunk a flat list of buttons into rows of at most `per_row`."""
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def _cancel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton("❌ Cancel", callback_data=CANCEL)]


# ─────────────────────────────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────────────────────────────
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add", callback_data="menu:add"),
                InlineKeyboardButton("📅 Check", callback_data="menu:check"),
            ],
            [
                InlineKeyboardButton("📊 Audit", callback_data="menu:audit"),
                InlineKeyboardButton("✏️ Change", callback_data="menu:change"),
            ],
            [
                InlineKeyboardButton("🗑️ Delete", callback_data="menu:delete"),
                InlineKeyboardButton("❓ Help", callback_data="menu:help"),
            ],
        ]
    )


def menu_button_kb() -> InlineKeyboardMarkup:
    """A single '🏠 Menu' button shown at the end of a finished flow."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu:home")]])


def day_kb(today: bool = True) -> InlineKeyboardMarkup:
    """'📅 Today' (optional) + a 1–31 grid (7 per row) + Cancel."""
    rows: list[list[InlineKeyboardButton]] = []
    if today:
        rows.append([InlineKeyboardButton("📅 Today", callback_data="day:today")])
    days = [InlineKeyboardButton(str(d), callback_data=f"day:{d}") for d in range(1, 32)]
    rows.extend(_rows(days, 7))
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def month_kb(today: bool = False) -> InlineKeyboardMarkup:
    """12 month buttons (Indonesian abbreviations, 3 per row) + Cancel.

    When `today` is set, a '📅 This month' shortcut is added at the top.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if today:
        rows.append([InlineKeyboardButton("📅 This month", callback_data="mon:today")])
    months = [
        InlineKeyboardButton(MONTH_NAMES_ID[m][:3], callback_data=f"mon:{m}")
        for m in range(1, 13)
    ]
    rows.extend(_rows(months, 3))
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def year_kb() -> InlineKeyboardMarkup:
    """Current year and the two previous years + Cancel."""
    y = now().year
    years = [InlineKeyboardButton(str(yr), callback_data=f"yr:{yr}") for yr in (y, y - 1, y - 2)]
    return InlineKeyboardMarkup([years, _cancel_row()])


def bank_kb(include_all: bool = False) -> InlineKeyboardMarkup:
    """One button per configured bank (2 per row) + Cancel.

    When `include_all` is set, a '🏦 All banks' shortcut is added at the top
    (used by Check as a "no filter" option).
    """
    rows: list[list[InlineKeyboardButton]] = []
    if include_all:
        rows.append([InlineKeyboardButton("🏦 All banks", callback_data="bank:all")])
    banks = [InlineKeyboardButton(b, callback_data=f"bank:{b}") for b in BANKS]
    rows.extend(_rows(banks, 2))
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def field_kb() -> InlineKeyboardMarkup:
    """Field picker for the Change flow."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💰 Amount", callback_data="fld:amount"),
                InlineKeyboardButton("📝 Notes", callback_data="fld:notes"),
            ],
            [
                InlineKeyboardButton("🏦 Bank", callback_data="fld:bank"),
                InlineKeyboardButton("📅 Date", callback_data="fld:date"),
            ],
            _cancel_row(),
        ]
    )


def confirm_kb(action: str = "submit") -> InlineKeyboardMarkup:
    """Confirm/Cancel keyboard. `action` is 'submit' (Add) or 'delete' (Delete)."""
    label = {"submit": "✅ Submit", "delete": "🗑️ Confirm delete"}.get(action, "✅ Confirm")
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=f"ok:{action}")],
            _cancel_row(),
        ]
    )


def cancel_kb() -> InlineKeyboardMarkup:
    """Just a Cancel button — shown while waiting for free-text input."""
    return InlineKeyboardMarkup([_cancel_row()])
