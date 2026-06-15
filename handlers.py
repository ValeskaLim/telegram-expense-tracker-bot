"""Telegram command handlers and shared response renderers for the bot.

The *renderers* (``render_*``) build the HTML reply strings and are reused by
both the typed command handlers below and the button flows in ``flows.py`` so
the output is identical no matter how the action was triggered.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from constant import BANKS, MONTH_NAMES_ID
from database import Database
from keyboards import main_menu_kb
from utils import (
    InputError,
    banks_help,
    esc,
    format_date_id,
    format_rupiah,
    normalize_bank,
    now,
    parse_add_args,
    parse_amount,
    parse_date_parts,
    parse_month,
    today,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Usage snippets (HTML)
# ─────────────────────────────────────────────────────────────────────────────
ADD_USAGE = (
    "<b>➕ Add an expense</b>\n"
    "Today:\n"
    "<code>/add Makan siang 16000 bca1</code>\n"
    "A date this year:\n"
    "<code>/add 16 Desember Makan siang 20000 bca1</code>\n"
    f"Bank: {banks_help()}"
)
CHECK_USAGE = (
    "<b>📅 Check a date</b>\n"
    "<code>/check 16 Desember 2026</code>\n"
    "<code>/check 16 December 2026 bca1</code> (optional bank filter)\n"
    "Month can be Indonesian or English."
)
AUDIT_USAGE = (
    "<b>📊 Monthly audit</b>\n<code>/audit Desember 2026</code>"
)
CHANGE_USAGE = (
    "<b>✏️ Change an entry</b>\n"
    "<code>/change &lt;id&gt; amount 25000</code>\n"
    "<code>/change &lt;id&gt; notes Makan malam</code>\n"
    "<code>/change &lt;id&gt; bank mandiri</code>\n"
    "<code>/change &lt;id&gt; date 17 Desember 2026</code>"
)
DELETE_USAGE = "<b>🗑️ Delete an entry</b>\n<code>/delete &lt;id&gt;</code>"

HELP_TEXT = (
    "👋 <b>Expense Tracker</b>\n\n"
    "Tap a button below, or use a command directly:\n\n"
    f"{ADD_USAGE}\n\n"
    f"{CHECK_USAGE}\n\n"
    f"{AUDIT_USAGE}\n\n"
    f"{CHANGE_USAGE}\n\n"
    f"{DELETE_USAGE}\n\n"
    "Each entry shows its <code>ID</code> in /check and /audit — use it with "
    "/change and /delete."
)

MENU_TEXT = (
    "👋 <b>Expense Tracker</b>\n\n"
    "Tap a button to get started — or type a command, e.g. "
    "<code>/add Makan 16000 bca1</code>."
)

_MANAGE_HINT = "Use <code>/change &lt;id&gt; …</code> or <code>/delete &lt;id&gt;</code> to manage entries."


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────
def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.bot_data["db"]


async def _reply(update: Update, text: str, reply_markup=None) -> None:
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def _error(update: Update, text: str) -> None:
    await _reply(update, f"❌ {text}")


def _format_entry(e: dict, *, with_date: bool = False) -> str:
    date_part = f"[{e['date'].day} {MONTH_NAMES_ID[e['date'].month]}] " if with_date else ""
    return (
        f"• <code>ID:{e['id']}</code> {date_part}{format_rupiah(e['amount'])} — "
        f"{esc(e['notes'])} 🏦 {esc(e['bank'])}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Shared renderers (used by both the typed handlers and the button flows)
# ─────────────────────────────────────────────────────────────────────────────
def render_saved(date, amount: int, notes: str, bank: str, expense_id: int) -> str:
    return (
        "✅ <b>Saved!</b>\n\n"
        f"📅 {format_date_id(date)}\n"
        f"💰 {format_rupiah(amount)}\n"
        f"📝 {esc(notes)}\n"
        f"🏦 {esc(bank)}\n"
        f"🔖 ID: <code>{expense_id}</code>"
    )


def render_updated(expense_id: int, field_label: str, old_display: str, new_display: str) -> str:
    return (
        "✏️ <b>Updated!</b>\n\n"
        f"🔖 ID: <code>{expense_id}</code>\n"
        f"{field_label}: {old_display} → {new_display}"
    )


def render_deleted(entry: dict) -> str:
    return (
        "🗑️ <b>Deleted!</b>\n\n"
        f"📅 {format_date_id(entry['date'])}\n"
        f"💰 {format_rupiah(entry['amount'])}\n"
        f"📝 {esc(entry['notes'])}\n"
        f"🏦 {esc(entry['bank'])}"
    )


def render_entry_card(entry: dict) -> str:
    """Multi-line card for a single entry (used in Change/Delete confirmations)."""
    return (
        f"🔖 ID: <code>{entry['id']}</code>\n"
        f"📅 {format_date_id(entry['date'])}\n"
        f"💰 {format_rupiah(entry['amount'])}\n"
        f"📝 {esc(entry['notes'])}\n"
        f"🏦 {esc(entry['bank'])}"
    )


def render_check(expenses: list[dict], date, bank: str | None) -> str:
    if not expenses:
        suffix = f" for bank <code>{esc(bank)}</code>" if bank else ""
        return f"📭 No expenses on <b>{format_date_id(date)}</b>{suffix}."
    total = sum(e["amount"] for e in expenses)
    lines = [f"📅 <b>{format_date_id(date)}</b>", ""]
    lines += [_format_entry(e) for e in expenses]
    lines += ["", f"💰 <b>Total: {format_rupiah(total)}</b>", "", _MANAGE_HINT]
    return "\n".join(lines)


def render_audit(expenses: list[dict], month: int, year: int) -> str:
    label = f"{MONTH_NAMES_ID[month]} {year}"
    if not expenses:
        return f"📭 No expenses for <b>{label}</b>."
    total = sum(e["amount"] for e in expenses)
    by_bank: dict[str, tuple[int, int]] = {}
    for e in expenses:
        count, amt = by_bank.get(e["bank"], (0, 0))
        by_bank[e["bank"]] = (count + 1, amt + e["amount"])

    # Known banks first (in configured order), then any legacy/unknown banks.
    ordered = [b for b in BANKS if b in by_bank] + [b for b in by_bank if b not in BANKS]

    lines = [
        f"📊 <b>Audit — {label}</b>",
        "",
        f"📝 Entries: {len(expenses)}",
        f"💰 <b>Total: {format_rupiah(total)}</b>",
        "",
        "<b>Per bank:</b>",
    ]
    for bank in ordered:
        count, amt = by_bank[bank]
        lines.append(f"• {esc(bank)}: {format_rupiah(amt)} ({count})")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# /start, /menu, /help and the 🏠 Menu / ❓ Help buttons
# ─────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start and /menu — show the main menu."""
    await _reply(update, MENU_TEXT, reply_markup=main_menu_kb())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — show the full command reference plus the menu."""
    await _reply(update, HELP_TEXT, reply_markup=main_menu_kb())


# ─────────────────────────────────────────────────────────────────────────────
# /add  (typed fast path)
# ─────────────────────────────────────────────────────────────────────────────
async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        date, notes, amount, bank = parse_add_args(
            context.args, year=now().year, default_date=today()
        )
    except InputError as e:
        await _reply(update, f"❌ {e}\n\n{ADD_USAGE}")
        return
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("Unexpected error parsing /add: %s", e)
        await _error(update, "Something went wrong. Please try again.")
        return

    try:
        expense_id = _db(context).add_expense(date, amount, notes, bank)
    except Exception as e:
        logger.exception("Failed to save expense: %s", e)
        await _error(update, "Could not save the expense. Please try again.")
        return

    await _reply(update, render_saved(date, amount, notes, bank, expense_id))
    logger.info("Saved expense id=%s amount=%s bank=%s", expense_id, amount, bank)


# ─────────────────────────────────────────────────────────────────────────────
# /check <day> <month> <year> [bank]  (typed fast path)
# ─────────────────────────────────────────────────────────────────────────────
async def check_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) < 3:
        await _reply(update, f"❌ Invalid format.\n\n{CHECK_USAGE}")
        return

    date = parse_date_parts(args[:3])
    if date is None:
        await _reply(update, f"❌ Invalid date.\n\n{CHECK_USAGE}")
        return

    bank = None
    if len(args) >= 4:
        bank = normalize_bank(args[3])
        if bank is None:
            await _error(update, f"Invalid bank <code>{esc(args[3])}</code>. Choose: {banks_help()}.")
            return

    try:
        expenses = _db(context).get_expenses_by_date(date, bank)
    except Exception as e:
        logger.exception("Failed /check query: %s", e)
        await _error(update, "Something went wrong. Please try again.")
        return

    await _reply(update, render_check(expenses, date, bank))
    logger.info("Checked date %s (%d entries)", date.date(), len(expenses))


# ─────────────────────────────────────────────────────────────────────────────
# /audit <month> <year>  (typed fast path)
# ─────────────────────────────────────────────────────────────────────────────
async def audit_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 2:
        await _reply(update, f"❌ Invalid format.\n\n{AUDIT_USAGE}")
        return

    month = parse_month(args[0])
    if month is None:
        await _error(update, f"<code>{esc(args[0])}</code> is not a valid month.")
        return
    try:
        year = int(args[1])
    except ValueError:
        await _error(update, f"<code>{esc(args[1])}</code> is not a valid year.")
        return

    try:
        expenses = _db(context).get_expenses_by_month(month, year)
    except Exception as e:
        logger.exception("Failed /audit query: %s", e)
        await _error(update, "Something went wrong. Please try again.")
        return

    await _reply(update, render_audit(expenses, month, year))
    logger.info("Audited %s %s (%d entries)", MONTH_NAMES_ID[month], year, len(expenses))


# ─────────────────────────────────────────────────────────────────────────────
# /delete <id>  (typed fast path)
# ─────────────────────────────────────────────────────────────────────────────
async def delete_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        await _reply(update, f"❌ Invalid format.\n\n{DELETE_USAGE}")
        return

    expense_id = int(args[0])
    db = _db(context)
    try:
        expense = db.get_expense_by_id(expense_id)
        if expense is None:
            await _error(update, f"No expense found with ID <code>{expense_id}</code>.")
            return
        db.delete_expense(expense_id)
    except Exception as e:
        logger.exception("Failed /delete: %s", e)
        await _error(update, "Something went wrong. Please try again.")
        return

    await _reply(update, render_deleted(expense))
    logger.info("Deleted expense id=%s", expense_id)


# ─────────────────────────────────────────────────────────────────────────────
# /change <id> <field> <value...>  (typed fast path)
# ─────────────────────────────────────────────────────────────────────────────
async def change_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) < 3 or not args[0].isdigit():
        await _reply(update, f"❌ Invalid format.\n\n{CHANGE_USAGE}")
        return

    expense_id = int(args[0])
    field = args[1].lower()
    raw = args[2:]

    db = _db(context)
    try:
        expense = db.get_expense_by_id(expense_id)
    except Exception as e:
        logger.exception("Failed /change lookup: %s", e)
        await _error(update, "Something went wrong. Please try again.")
        return
    if expense is None:
        await _error(update, f"No expense found with ID <code>{expense_id}</code>.")
        return

    # Validate the requested change and build a human-readable summary.
    kwargs: dict = {}
    old_display: str
    new_display: str
    if field in ("amount", "amt", "nominal"):
        amount = parse_amount(" ".join(raw))
        if amount is None:
            await _error(update, f"Invalid amount <code>{esc(' '.join(raw))}</code>.")
            return
        kwargs["amount"] = amount
        old_display = format_rupiah(expense["amount"])
        new_display = format_rupiah(amount)
        field_label = "💰 Amount"
    elif field in ("notes", "note", "catatan"):
        notes = " ".join(raw).strip()
        if not notes:
            await _error(update, "Please provide the new note.")
            return
        kwargs["notes"] = notes
        old_display = esc(expense["notes"])
        new_display = esc(notes)
        field_label = "📝 Notes"
    elif field == "bank":
        bank = normalize_bank(" ".join(raw))
        if bank is None:
            await _error(update, f"Invalid bank <code>{esc(' '.join(raw))}</code>. Choose: {banks_help()}.")
            return
        kwargs["bank"] = bank
        old_display = esc(expense["bank"])
        new_display = esc(bank)
        field_label = "🏦 Bank"
    elif field in ("date", "tanggal"):
        date = parse_date_parts(raw)
        if date is None:
            await _error(update, f"Invalid date <code>{esc(' '.join(raw))}</code>.")
            return
        kwargs["date"] = date
        old_display = format_date_id(expense["date"])
        new_display = format_date_id(date)
        field_label = "📅 Date"
    else:
        await _error(
            update,
            f"Unknown field <code>{esc(field)}</code>. "
            "Use <code>amount</code>, <code>notes</code>, <code>bank</code>, or <code>date</code>.",
        )
        return

    try:
        db.update_expense(expense_id, **kwargs)
    except Exception as e:
        logger.exception("Failed /change update: %s", e)
        await _error(update, "Something went wrong. Please try again.")
        return

    await _reply(update, render_updated(expense_id, field_label, old_display, new_display))
    logger.info("Updated expense id=%s field=%s", expense_id, field)


# ─────────────────────────────────────────────────────────────────────────────
# Fallbacks
# ─────────────────────────────────────────────────────────────────────────────
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, "🤔 Unknown command. Send /menu to see what I can do.")


async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(
        update,
        "💡 Tap a button to get started:",
        reply_markup=main_menu_kb(),
    )
