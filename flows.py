"""Button-driven conversation flows for the Expense Tracker bot.

The UI is built from ``ReplyKeyboardMarkup`` panels that pop up at the text
input. Tapping a button sends its label as a message, so every step is handled
by a text ``MessageHandler`` and interpreted in the context of the current
conversation state. Typed steps (notes / nominal / ID) show a labeled
placeholder in the input box so each value is clearly tied to one field.

Each flow can be started by tapping its menu button (which sends e.g. "➕ Add")
or by sending the bare command (``/add``). A command *with* arguments runs the
original typed handler instead — the power-user fast path.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import handlers
import keyboards as kb
from constant import MONTH_NAMES_ID
from handlers import (
    render_audit,
    render_check,
    render_deleted,
    render_entry_card,
    render_saved,
    render_updated,
)
from utils import (
    esc,
    format_date_id,
    format_rupiah,
    make_date,
    normalize_bank,
    now,
    parse_amount,
    parse_month,
    today,
)

logger = logging.getLogger(__name__)

# Conversation states.
(
    ADD_DAY,
    ADD_MONTH,
    ADD_NOTES,
    ADD_AMOUNT,
    ADD_BANK,
    ADD_CONFIRM,
    CHECK_DAY,
    CHECK_MONTH,
    CHECK_YEAR,
    CHECK_BANK,
    AUDIT_MONTH,
    AUDIT_YEAR,
    CHANGE_ID,
    CHANGE_FIELD,
    CHANGE_AMOUNT,
    CHANGE_NOTES,
    CHANGE_BANK,
    CHANGE_DATE_DAY,
    CHANGE_DATE_MONTH,
    DELETE_ID,
    DELETE_CONFIRM,
) = range(21)


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────
def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["db"]


def _rec(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("rec", {})


def _txt(update: Update) -> str:
    return (update.message.text or "").strip()


async def _send(update: Update, text: str, markup) -> None:
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


def _end(context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return ConversationHandler.END


def _day_value(text: str):
    """Return 'today', an int day, or None."""
    if text == kb.TODAY:
        return "today"
    if text.isdigit() and 1 <= int(text) <= 31:
        return int(text)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Cancel
# ─────────────────────────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await _send(update, "❌ Cancelled.", kb.main_menu_kb())
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# Entry points
# ─────────────────────────────────────────────────────────────────────────────
async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:  # /add Makan 16000 bca1
        await handlers.add_expense(update, context)
        return ConversationHandler.END
    return await _add_start(update, context)


async def check_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await handlers.check_date(update, context)
        return ConversationHandler.END
    return await _check_start(update, context)


async def audit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await handlers.audit_month(update, context)
        return ConversationHandler.END
    return await _audit_start(update, context)


async def change_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await handlers.change_expense(update, context)
        return ConversationHandler.END
    return await _change_start(update, context)


async def delete_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await handlers.delete_expense(update, context)
        return ConversationHandler.END
    return await _delete_start(update, context)


async def help_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await handlers.help_cmd(update, context)
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# Add flow
# ─────────────────────────────────────────────────────────────────────────────
async def _add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {"year": now().year}
    await _send(update, "➕ <b>Add expense</b> · Step 1/5\nPick the <b>date</b>:", kb.day_kb())
    return ADD_DAY


async def add_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    val = _day_value(_txt(update))
    if val == "today":
        d = today()
        rec.update(day=d.day, month=d.month, year=d.year, date=d)
        return await _add_ask_notes(update, context)
    if isinstance(val, int):
        rec["day"] = val
        await _send(update, "➕ Step 2/5\nPick the <b>month</b>:", kb.month_kb())
        return ADD_MONTH
    await _send(update, "⚠️ Tap a day 1–31 or 📅 Today.", kb.day_kb())
    return ADD_DAY


async def add_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    month = parse_month(_txt(update))
    if month is None:
        await _send(update, "⚠️ Tap a month.", kb.month_kb())
        return ADD_MONTH
    date = make_date(rec["day"], month, rec["year"])
    if date is None:
        await _send(update, f"⚠️ {rec['day']} {MONTH_NAMES_ID[month]} isn't a real date. Pick another month:", kb.month_kb())
        return ADD_MONTH
    rec.update(month=month, date=date)
    return await _add_ask_notes(update, context)


async def _add_ask_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _send(update, "➕ Step 3/5\n📝 Type the <b>notes</b>:", kb.text_kb("e.g. Makan siang"))
    return ADD_NOTES


async def add_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    notes = _txt(update)
    if not notes:
        await _send(update, "⚠️ Notes can't be empty. Type the notes:", kb.text_kb("e.g. Makan siang"))
        return ADD_NOTES
    rec["notes"] = notes
    await _send(update, "➕ Step 4/5\n💰 Type the <b>nominal</b>:", kb.text_kb("e.g. 50000"))
    return ADD_AMOUNT


async def add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    amount = parse_amount(_txt(update))
    if amount is None:
        await _send(update, "⚠️ Invalid amount. Type a whole number, e.g. 50000:", kb.text_kb("e.g. 50000"))
        return ADD_AMOUNT
    rec["amount"] = amount
    await _send(update, "➕ Step 5/5\nPick the <b>bank</b>:", kb.bank_kb())
    return ADD_BANK


async def add_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    bank = normalize_bank(_txt(update))
    if bank is None:
        await _send(update, "⚠️ Tap one of the bank buttons.", kb.bank_kb())
        return ADD_BANK
    rec["bank"] = bank
    summary = (
        "➕ <b>Review</b>\n\n"
        f"📅 {format_date_id(rec['date'])}\n"
        f"📝 {esc(rec['notes'])}\n"
        f"💰 {format_rupiah(rec['amount'])}\n"
        f"🏦 {esc(rec['bank'])}\n\n"
        "Tap ✅ Submit to save."
    )
    await _send(update, summary, kb.confirm_kb("submit"))
    return ADD_CONFIRM


async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    if _txt(update) != kb.SUBMIT:
        await _send(update, "Tap ✅ Submit or ❌ Cancel.", kb.confirm_kb("submit"))
        return ADD_CONFIRM
    try:
        expense_id = _db(context).add_expense(rec["date"], rec["amount"], rec["notes"], rec["bank"])
    except Exception as e:
        logger.exception("Flow /add save failed: %s", e)
        await _send(update, "❌ Could not save the expense. Please try again.", kb.main_menu_kb())
        return _end(context)
    await _send(update, render_saved(rec["date"], rec["amount"], rec["notes"], rec["bank"], expense_id), kb.main_menu_kb())
    logger.info("Flow saved expense id=%s bank=%s", expense_id, rec["bank"])
    return _end(context)


# ─────────────────────────────────────────────────────────────────────────────
# Check flow
# ─────────────────────────────────────────────────────────────────────────────
async def _check_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {"year": now().year}
    await _send(update, "📅 <b>Check a date</b>\nPick the <b>date</b> (or 📅 Today):", kb.day_kb())
    return CHECK_DAY


async def check_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    val = _day_value(_txt(update))
    if val == "today":
        d = today()
        rec.update(day=d.day, month=d.month, year=d.year, date=d)
        return await _check_ask_bank(update, context)
    if isinstance(val, int):
        rec["day"] = val
        await _send(update, "📅 Pick the <b>month</b>:", kb.month_kb())
        return CHECK_MONTH
    await _send(update, "⚠️ Tap a day 1–31 or 📅 Today.", kb.day_kb())
    return CHECK_DAY


async def check_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    month = parse_month(_txt(update))
    if month is None:
        await _send(update, "⚠️ Tap a month.", kb.month_kb())
        return CHECK_MONTH
    rec["month"] = month
    await _send(update, "📅 Pick the <b>year</b>:", kb.year_kb())
    return CHECK_YEAR


async def check_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    t = _txt(update)
    if not (t.isdigit() and len(t) == 4):
        await _send(update, "⚠️ Tap a year.", kb.year_kb())
        return CHECK_YEAR
    date = make_date(rec["day"], rec["month"], int(t))
    if date is None:
        await _send(update, f"⚠️ {rec['day']} {MONTH_NAMES_ID[rec['month']]} {t} isn't valid. Pick another year:", kb.year_kb())
        return CHECK_YEAR
    rec.update(year=int(t), date=date)
    return await _check_ask_bank(update, context)


async def _check_ask_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _send(update, "📅 Filter by <b>bank</b>:", kb.bank_kb(include_all=True))
    return CHECK_BANK


async def check_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    t = _txt(update)
    if t == kb.ALL_BANKS:
        bank = None
    else:
        bank = normalize_bank(t)
        if bank is None:
            await _send(update, "⚠️ Tap a bank or 🏦 All banks.", kb.bank_kb(include_all=True))
            return CHECK_BANK
    try:
        expenses = _db(context).get_expenses_by_date(rec["date"], bank)
    except Exception as e:
        logger.exception("Flow /check query failed: %s", e)
        await _send(update, "❌ Something went wrong. Please try again.", kb.main_menu_kb())
        return _end(context)
    await _send(update, render_check(expenses, rec["date"], bank), kb.main_menu_kb())
    return _end(context)


# ─────────────────────────────────────────────────────────────────────────────
# Audit flow
# ─────────────────────────────────────────────────────────────────────────────
async def _audit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {}
    await _send(update, "📊 <b>Monthly audit</b>\nPick the <b>month</b> (or 📅 This month):", kb.month_kb(today=True))
    return AUDIT_MONTH


async def audit_month_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    t = _txt(update)
    if t == kb.THIS_MONTH:
        n = now()
        rec.update(month=n.month, year=n.year)
        return await _audit_render(update, context)
    month = parse_month(t)
    if month is None:
        await _send(update, "⚠️ Tap a month.", kb.month_kb(today=True))
        return AUDIT_MONTH
    rec["month"] = month
    await _send(update, "📊 Pick the <b>year</b>:", kb.year_kb())
    return AUDIT_YEAR


async def audit_year_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    t = _txt(update)
    if not (t.isdigit() and len(t) == 4):
        await _send(update, "⚠️ Tap a year.", kb.year_kb())
        return AUDIT_YEAR
    rec["year"] = int(t)
    return await _audit_render(update, context)


async def _audit_render(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    try:
        expenses = _db(context).get_expenses_by_month(rec["month"], rec["year"])
    except Exception as e:
        logger.exception("Flow /audit query failed: %s", e)
        await _send(update, "❌ Something went wrong. Please try again.", kb.main_menu_kb())
        return _end(context)
    await _send(update, render_audit(expenses, rec["month"], rec["year"]), kb.main_menu_kb())
    return _end(context)


# ─────────────────────────────────────────────────────────────────────────────
# Change flow
# ─────────────────────────────────────────────────────────────────────────────
async def _change_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {}
    await _send(update, "✏️ <b>Change an entry</b>\nType the entry <b>ID</b> (see 📅 Check / 📊 Audit):", kb.text_kb("e.g. 5"))
    return CHANGE_ID


async def change_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    t = _txt(update)
    if not t.isdigit():
        await _send(update, "⚠️ Type a numeric ID:", kb.text_kb("e.g. 5"))
        return CHANGE_ID
    entry = _db(context).get_expense_by_id(int(t))
    if entry is None:
        await _send(update, f"❌ No entry with ID <code>{esc(t)}</code>. Type another ID:", kb.text_kb("e.g. 5"))
        return CHANGE_ID
    _rec(context)["entry"] = entry
    await _send(update, "✏️ <b>Change an entry</b>\n\n" + render_entry_card(entry) + "\n\nPick the <b>field</b> to change:", kb.field_kb())
    return CHANGE_FIELD


async def change_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    field = kb.FIELD_LABELS.get(_txt(update))
    if field is None:
        await _send(update, "⚠️ Tap a field.", kb.field_kb())
        return CHANGE_FIELD
    rec["field"] = field
    if field == "amount":
        await _send(update, "💰 Type the new <b>nominal</b>:", kb.text_kb("e.g. 50000"))
        return CHANGE_AMOUNT
    if field == "notes":
        await _send(update, "📝 Type the new <b>notes</b>:", kb.text_kb("e.g. Makan siang"))
        return CHANGE_NOTES
    if field == "bank":
        await _send(update, "🏦 Pick the new <b>bank</b>:", kb.bank_kb())
        return CHANGE_BANK
    rec["year"] = now().year
    await _send(update, "📅 Pick the new <b>date</b>:", kb.day_kb())
    return CHANGE_DATE_DAY


async def _apply_change(update: Update, context: ContextTypes.DEFAULT_TYPE, *, label: str, old: str, new: str, **fields) -> int:
    entry = _rec(context)["entry"]
    try:
        _db(context).update_expense(entry["id"], **fields)
    except Exception as e:
        logger.exception("Flow /change update failed: %s", e)
        await _send(update, "❌ Something went wrong. Please try again.", kb.main_menu_kb())
        return _end(context)
    await _send(update, render_updated(entry["id"], label, old, new), kb.main_menu_kb())
    logger.info("Flow updated expense id=%s field=%s", entry["id"], label)
    return _end(context)


async def change_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    entry = _rec(context)["entry"]
    amount = parse_amount(_txt(update))
    if amount is None:
        await _send(update, "⚠️ Invalid amount. Type a whole number, e.g. 50000:", kb.text_kb("e.g. 50000"))
        return CHANGE_AMOUNT
    return await _apply_change(update, context, amount=amount, label="💰 Amount",
                               old=format_rupiah(entry["amount"]), new=format_rupiah(amount))


async def change_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    entry = _rec(context)["entry"]
    notes = _txt(update)
    if not notes:
        await _send(update, "⚠️ Notes can't be empty. Type the new notes:", kb.text_kb("e.g. Makan siang"))
        return CHANGE_NOTES
    return await _apply_change(update, context, notes=notes, label="📝 Notes",
                               old=esc(entry["notes"]), new=esc(notes))


async def change_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    entry = _rec(context)["entry"]
    bank = normalize_bank(_txt(update))
    if bank is None:
        await _send(update, "⚠️ Tap one of the bank buttons.", kb.bank_kb())
        return CHANGE_BANK
    return await _apply_change(update, context, bank=bank, label="🏦 Bank",
                               old=esc(entry["bank"]), new=esc(bank))


async def change_date_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    entry = rec["entry"]
    val = _day_value(_txt(update))
    if val == "today":
        d = today()
        return await _apply_change(update, context, date=d, label="📅 Date",
                                   old=format_date_id(entry["date"]), new=format_date_id(d))
    if isinstance(val, int):
        rec["day"] = val
        await _send(update, "📅 Pick the new <b>month</b>:", kb.month_kb())
        return CHANGE_DATE_MONTH
    await _send(update, "⚠️ Tap a day 1–31 or 📅 Today.", kb.day_kb())
    return CHANGE_DATE_DAY


async def change_date_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    entry = rec["entry"]
    month = parse_month(_txt(update))
    if month is None:
        await _send(update, "⚠️ Tap a month.", kb.month_kb())
        return CHANGE_DATE_MONTH
    date = make_date(rec["day"], month, rec["year"])
    if date is None:
        await _send(update, f"⚠️ {rec['day']} {MONTH_NAMES_ID[month]} isn't a real date. Pick another month:", kb.month_kb())
        return CHANGE_DATE_MONTH
    return await _apply_change(update, context, date=date, label="📅 Date",
                               old=format_date_id(entry["date"]), new=format_date_id(date))


# ─────────────────────────────────────────────────────────────────────────────
# Delete flow
# ─────────────────────────────────────────────────────────────────────────────
async def _delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {}
    await _send(update, "🗑️ <b>Delete an entry</b>\nType the entry <b>ID</b>:", kb.text_kb("e.g. 5"))
    return DELETE_ID


async def delete_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    t = _txt(update)
    if not t.isdigit():
        await _send(update, "⚠️ Type a numeric ID:", kb.text_kb("e.g. 5"))
        return DELETE_ID
    entry = _db(context).get_expense_by_id(int(t))
    if entry is None:
        await _send(update, f"❌ No entry with ID <code>{esc(t)}</code>. Type another ID:", kb.text_kb("e.g. 5"))
        return DELETE_ID
    _rec(context)["entry"] = entry
    await _send(update, "🗑️ <b>Delete this entry?</b>\n\n" + render_entry_card(entry), kb.confirm_kb("delete"))
    return DELETE_CONFIRM


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    entry = _rec(context)["entry"]
    if _txt(update) != kb.CONFIRM_DELETE:
        await _send(update, "Tap 🗑️ Confirm delete or ❌ Cancel.", kb.confirm_kb("delete"))
        return DELETE_CONFIRM
    try:
        _db(context).delete_expense(entry["id"])
    except Exception as e:
        logger.exception("Flow /delete failed: %s", e)
        await _send(update, "❌ Something went wrong. Please try again.", kb.main_menu_kb())
        return _end(context)
    await _send(update, render_deleted(entry), kb.main_menu_kb())
    logger.info("Flow deleted expense id=%s", entry["id"])
    return _end(context)


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────
def build_conversation() -> ConversationHandler:
    cancel_handler = MessageHandler(filters.Text([kb.CANCEL]), cancel)

    def state(fn) -> list:
        # Cancel is checked first; everything else goes to the step handler.
        return [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, fn)]

    return ConversationHandler(
        entry_points=[
            CommandHandler("add", add_entry),
            CommandHandler("check", check_entry),
            CommandHandler("audit", audit_entry),
            CommandHandler("change", change_entry),
            CommandHandler("delete", delete_entry),
            MessageHandler(filters.Text([kb.MENU_ADD]), add_entry),
            MessageHandler(filters.Text([kb.MENU_CHECK]), check_entry),
            MessageHandler(filters.Text([kb.MENU_AUDIT]), audit_entry),
            MessageHandler(filters.Text([kb.MENU_CHANGE]), change_entry),
            MessageHandler(filters.Text([kb.MENU_DELETE]), delete_entry),
            MessageHandler(filters.Text([kb.MENU_HELP]), help_entry),
        ],
        states={
            ADD_DAY: state(add_day),
            ADD_MONTH: state(add_month),
            ADD_NOTES: state(add_notes),
            ADD_AMOUNT: state(add_amount),
            ADD_BANK: state(add_bank),
            ADD_CONFIRM: state(add_confirm),
            CHECK_DAY: state(check_day),
            CHECK_MONTH: state(check_month),
            CHECK_YEAR: state(check_year),
            CHECK_BANK: state(check_bank),
            AUDIT_MONTH: state(audit_month_pick),
            AUDIT_YEAR: state(audit_year_pick),
            CHANGE_ID: state(change_id),
            CHANGE_FIELD: state(change_field),
            CHANGE_AMOUNT: state(change_amount),
            CHANGE_NOTES: state(change_notes),
            CHANGE_BANK: state(change_bank),
            CHANGE_DATE_DAY: state(change_date_day),
            CHANGE_DATE_MONTH: state(change_date_month),
            DELETE_ID: state(delete_id),
            DELETE_CONFIRM: state(delete_confirm),
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="expense_wizard",
        allow_reentry=True,
    )
