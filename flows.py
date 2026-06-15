"""Button-driven conversation flows for the Expense Tracker bot.

One ``ConversationHandler`` drives every action (Add / Check / Audit / Change /
Delete). Each flow keeps a single *form* message in ``context.user_data`` and
edits it in place as the user taps through the steps, so the chat shows one
tidy, evolving card instead of a wall of prompts.

Each flow can be entered two ways:
  * tapping a button on the main menu (``menu:<action>`` callback), or
  * sending the bare command (``/add`` with no arguments).
Sending a command *with* arguments runs the original typed handler instead
(the power-user fast path), so nothing about the old commands changes.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import handlers
from constant import MONTH_NAMES_ID
from handlers import (
    render_audit,
    render_check,
    render_deleted,
    render_entry_card,
    render_saved,
    render_updated,
)
from keyboards import (
    bank_kb,
    cancel_kb,
    confirm_kb,
    day_kb,
    field_kb,
    main_menu_kb,
    menu_button_kb,
    month_kb,
    year_kb,
)
from utils import (
    esc,
    format_date_id,
    format_rupiah,
    make_date,
    normalize_bank,
    now,
    parse_amount,
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
# Form-message plumbing
# ─────────────────────────────────────────────────────────────────────────────
def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["db"]


def _rec(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("rec", {})


async def _show_form(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup) -> None:
    """Start (or restart) a flow's form message and remember where it lives.

    Edits the triggering callback message into the form when entered from a
    menu button; otherwise sends a fresh message for a bare command.
    """
    q = update.callback_query
    if q is not None:
        await q.answer()
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            chat_id, msg_id = q.message.chat_id, q.message.message_id
        except BadRequest:
            m = await q.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            chat_id, msg_id = m.chat_id, m.message_id
    else:
        m = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        chat_id, msg_id = m.chat_id, m.message_id
    context.user_data["form_chat_id"] = chat_id
    context.user_data["form_msg_id"] = msg_id


async def _edit_form(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None) -> None:
    """Edit the stored form message, ignoring the harmless 'not modified' error."""
    try:
        await context.bot.edit_message_text(
            chat_id=context.user_data["form_chat_id"],
            message_id=context.user_data["form_msg_id"],
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


def _end(context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# Form text builders
# ─────────────────────────────────────────────────────────────────────────────
def _date_display(rec: dict) -> str:
    if rec.get("date"):
        return format_date_id(rec["date"])
    if rec.get("day"):
        return f"{rec['day']} … {rec.get('year', now().year)}"
    return "—"


def _add_form_text(rec: dict, hint: str) -> str:
    notes = esc(rec["notes"]) if rec.get("notes") else "—"
    amount = format_rupiah(rec["amount"]) if rec.get("amount") is not None else "—"
    bank = esc(rec["bank"]) if rec.get("bank") else "—"
    return (
        "➕ <b>New Expense</b>\n\n"
        f"📅 Date: {_date_display(rec)}\n"
        f"📝 Notes: {notes}\n"
        f"💰 Amount: {amount}\n"
        f"🏦 Bank: {bank}\n\n"
        f"{hint}"
    )


def _check_form_text(rec: dict, hint: str) -> str:
    bank = rec.get("bank")
    bank_disp = "All banks" if bank == "all" else (esc(bank) if bank else "—")
    return (
        "📅 <b>Check a date</b>\n\n"
        f"📅 Date: {_date_display(rec)}\n"
        f"🏦 Bank: {bank_disp}\n\n"
        f"{hint}"
    )


def _audit_form_text(rec: dict, hint: str) -> str:
    month = MONTH_NAMES_ID[rec["month"]] if rec.get("month") else "—"
    year = rec.get("year", "—")
    return (
        "📊 <b>Monthly audit</b>\n\n"
        f"🗓️ Month: {month}\n"
        f"📅 Year: {year}\n\n"
        f"{hint}"
    )


def _id_prompt(title: str, note: str = "") -> str:
    extra = f"\n\n{note}" if note else ""
    return (
        f"{title}\n\n"
        "Send the <b>ID</b> of the entry — you can find IDs with 📅 Check or 📊 Audit."
        f"{extra}"
    )


def _change_field_text(entry: dict, hint: str) -> str:
    return "✏️ <b>Change an entry</b>\n\n" + render_entry_card(entry) + f"\n\n{hint}"


# ─────────────────────────────────────────────────────────────────────────────
# Entry points
# ─────────────────────────────────────────────────────────────────────────────
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Route a main-menu button tap into the matching flow."""
    action = update.callback_query.data.split(":", 1)[1]
    starters = {
        "add": _add_start,
        "check": _check_start,
        "audit": _audit_start,
        "change": _change_start,
        "delete": _delete_start,
    }
    starter = starters.get(action)
    if starter is None:  # pragma: no cover - pattern already restricts this
        await update.callback_query.answer()
        return ConversationHandler.END
    return await starter(update, context)


async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:  # typed fast path: /add Makan 16000 bca1
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


# ─────────────────────────────────────────────────────────────────────────────
# Add flow
# ─────────────────────────────────────────────────────────────────────────────
async def _add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {"year": now().year}
    await _show_form(update, context, _add_form_text(_rec(context), "Pick the day:"), day_kb())
    return ADD_DAY


async def add_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    data = q.data.split(":", 1)[1]
    if data == "today":
        t = today()
        rec.update(day=t.day, month=t.month, year=t.year, date=t)
        await _edit_form(context, _add_form_text(rec, "Type the note:"), cancel_kb())
        return ADD_NOTES
    rec["day"] = int(data)
    await _edit_form(context, _add_form_text(rec, "Pick the month:"), month_kb())
    return ADD_MONTH


async def add_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    month = int(q.data.split(":", 1)[1])
    date = make_date(rec["day"], month, rec["year"])
    if date is None:
        hint = f"⚠️ {rec['day']} {MONTH_NAMES_ID[month]} isn't a real date. Pick another month:"
        await _edit_form(context, _add_form_text(rec, hint), month_kb())
        return ADD_MONTH
    rec.update(month=month, date=date)
    await _edit_form(context, _add_form_text(rec, "Type the note:"), cancel_kb())
    return ADD_NOTES


async def add_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    notes = (update.message.text or "").strip()
    if not notes:
        await _edit_form(context, _add_form_text(rec, "⚠️ Note can't be empty. Type the note:"), cancel_kb())
        return ADD_NOTES
    rec["notes"] = notes
    await _edit_form(context, _add_form_text(rec, "Type the amount (e.g. 50000):"), cancel_kb())
    return ADD_AMOUNT


async def add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    amount = parse_amount(update.message.text or "")
    if amount is None:
        await _edit_form(context, _add_form_text(rec, "⚠️ Invalid amount. Type a whole number, e.g. 50000:"), cancel_kb())
        return ADD_AMOUNT
    rec["amount"] = amount
    await _edit_form(context, _add_form_text(rec, "Pick the bank:"), bank_kb())
    return ADD_BANK


async def add_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    bank = q.data.split(":", 1)[1]
    if normalize_bank(bank) is None:
        await q.answer("Invalid bank.", show_alert=True)
        return ADD_BANK
    rec["bank"] = bank
    await _edit_form(context, _add_form_text(rec, "Review and submit:"), confirm_kb("submit"))
    return ADD_CONFIRM


async def add_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    try:
        expense_id = _db(context).add_expense(rec["date"], rec["amount"], rec["notes"], rec["bank"])
    except Exception as e:
        logger.exception("Flow /add save failed: %s", e)
        await _edit_form(context, "❌ Could not save the expense. Please try again.", menu_button_kb())
        return _end(context)
    await _edit_form(
        context,
        render_saved(rec["date"], rec["amount"], rec["notes"], rec["bank"], expense_id),
        menu_button_kb(),
    )
    logger.info("Flow saved expense id=%s bank=%s", expense_id, rec["bank"])
    return _end(context)


# ─────────────────────────────────────────────────────────────────────────────
# Check flow
# ─────────────────────────────────────────────────────────────────────────────
async def _check_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {"year": now().year}
    await _show_form(update, context, _check_form_text(_rec(context), "Pick the day (or Today):"), day_kb())
    return CHECK_DAY


async def check_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    data = q.data.split(":", 1)[1]
    if data == "today":
        t = today()
        rec.update(day=t.day, month=t.month, year=t.year, date=t)
        await _edit_form(context, _check_form_text(rec, "Filter by bank:"), bank_kb(include_all=True))
        return CHECK_BANK
    rec["day"] = int(data)
    await _edit_form(context, _check_form_text(rec, "Pick the month:"), month_kb())
    return CHECK_MONTH


async def check_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    rec["month"] = int(q.data.split(":", 1)[1])
    await _edit_form(context, _check_form_text(rec, "Pick the year:"), year_kb())
    return CHECK_YEAR


async def check_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    year = int(q.data.split(":", 1)[1])
    date = make_date(rec["day"], rec["month"], year)
    if date is None:
        hint = f"⚠️ {rec['day']} {MONTH_NAMES_ID[rec['month']]} {year} isn't valid. Pick another year:"
        await _edit_form(context, _check_form_text(rec, hint), year_kb())
        return CHECK_YEAR
    rec.update(year=year, date=date)
    await _edit_form(context, _check_form_text(rec, "Filter by bank:"), bank_kb(include_all=True))
    return CHECK_BANK


async def check_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    val = q.data.split(":", 1)[1]
    bank = None if val == "all" else val
    if bank is not None and normalize_bank(bank) is None:
        await q.answer("Invalid bank.", show_alert=True)
        return CHECK_BANK
    try:
        expenses = _db(context).get_expenses_by_date(rec["date"], bank)
    except Exception as e:
        logger.exception("Flow /check query failed: %s", e)
        await _edit_form(context, "❌ Something went wrong. Please try again.", menu_button_kb())
        return _end(context)
    await _edit_form(context, render_check(expenses, rec["date"], bank), menu_button_kb())
    return _end(context)


# ─────────────────────────────────────────────────────────────────────────────
# Audit flow
# ─────────────────────────────────────────────────────────────────────────────
async def _audit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {}
    await _show_form(update, context, _audit_form_text(_rec(context), "Pick the month (or This month):"), month_kb(today=True))
    return AUDIT_MONTH


async def _audit_render(context: ContextTypes.DEFAULT_TYPE) -> int:
    rec = _rec(context)
    try:
        expenses = _db(context).get_expenses_by_month(rec["month"], rec["year"])
    except Exception as e:
        logger.exception("Flow /audit query failed: %s", e)
        await _edit_form(context, "❌ Something went wrong. Please try again.", menu_button_kb())
        return _end(context)
    await _edit_form(context, render_audit(expenses, rec["month"], rec["year"]), menu_button_kb())
    return _end(context)


async def audit_month_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    val = q.data.split(":", 1)[1]
    if val == "today":
        n = now()
        rec.update(month=n.month, year=n.year)
        return await _audit_render(context)
    rec["month"] = int(val)
    await _edit_form(context, _audit_form_text(rec, "Pick the year:"), year_kb())
    return AUDIT_YEAR


async def audit_year_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    rec["year"] = int(q.data.split(":", 1)[1])
    return await _audit_render(context)


# ─────────────────────────────────────────────────────────────────────────────
# Change flow
# ─────────────────────────────────────────────────────────────────────────────
async def _change_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {}
    await _show_form(update, context, _id_prompt("✏️ <b>Change an entry</b>"), cancel_kb())
    return CHANGE_ID


async def change_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not text.isdigit():
        await _edit_form(context, _id_prompt("✏️ <b>Change an entry</b>", "⚠️ Send a numeric ID."), cancel_kb())
        return CHANGE_ID
    entry = _db(context).get_expense_by_id(int(text))
    if entry is None:
        await _edit_form(
            context,
            _id_prompt("✏️ <b>Change an entry</b>", f"❌ No entry with ID <code>{esc(text)}</code>."),
            cancel_kb(),
        )
        return CHANGE_ID
    _rec(context)["entry"] = entry
    await _edit_form(context, _change_field_text(entry, "Which field do you want to change?"), field_kb())
    return CHANGE_FIELD


async def change_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    field = q.data.split(":", 1)[1]
    rec["field"] = field
    entry = rec["entry"]
    if field == "amount":
        await _edit_form(context, _change_field_text(entry, "Type the new amount (e.g. 50000):"), cancel_kb())
        return CHANGE_AMOUNT
    if field == "notes":
        await _edit_form(context, _change_field_text(entry, "Type the new note:"), cancel_kb())
        return CHANGE_NOTES
    if field == "bank":
        await _edit_form(context, _change_field_text(entry, "Pick the new bank:"), bank_kb())
        return CHANGE_BANK
    # date
    rec["year"] = now().year
    await _edit_form(context, _change_field_text(entry, "Pick the new day:"), day_kb())
    return CHANGE_DATE_DAY


async def _apply_change(context: ContextTypes.DEFAULT_TYPE, *, label: str, old: str, new: str, **fields) -> int:
    entry = _rec(context)["entry"]
    try:
        _db(context).update_expense(entry["id"], **fields)
    except Exception as e:
        logger.exception("Flow /change update failed: %s", e)
        await _edit_form(context, "❌ Something went wrong. Please try again.", menu_button_kb())
        return _end(context)
    await _edit_form(context, render_updated(entry["id"], label, old, new), menu_button_kb())
    logger.info("Flow updated expense id=%s field=%s", entry["id"], label)
    return _end(context)


async def change_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    entry = _rec(context)["entry"]
    amount = parse_amount(update.message.text or "")
    if amount is None:
        await _edit_form(context, _change_field_text(entry, "⚠️ Invalid amount. Type a whole number, e.g. 50000:"), cancel_kb())
        return CHANGE_AMOUNT
    return await _apply_change(
        context, amount=amount, label="💰 Amount",
        old=format_rupiah(entry["amount"]), new=format_rupiah(amount),
    )


async def change_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    entry = _rec(context)["entry"]
    notes = (update.message.text or "").strip()
    if not notes:
        await _edit_form(context, _change_field_text(entry, "⚠️ Note can't be empty. Type the new note:"), cancel_kb())
        return CHANGE_NOTES
    return await _apply_change(
        context, notes=notes, label="📝 Notes",
        old=esc(entry["notes"]), new=esc(notes),
    )


async def change_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    entry = _rec(context)["entry"]
    bank = q.data.split(":", 1)[1]
    if normalize_bank(bank) is None:
        await q.answer("Invalid bank.", show_alert=True)
        return CHANGE_BANK
    return await _apply_change(
        context, bank=bank, label="🏦 Bank",
        old=esc(entry["bank"]), new=esc(bank),
    )


async def change_date_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    entry = rec["entry"]
    data = q.data.split(":", 1)[1]
    if data == "today":
        t = today()
        return await _apply_change(
            context, date=t, label="📅 Date",
            old=format_date_id(entry["date"]), new=format_date_id(t),
        )
    rec["day"] = int(data)
    await _edit_form(context, _change_field_text(entry, "Pick the new month:"), month_kb())
    return CHANGE_DATE_MONTH


async def change_date_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    rec = _rec(context)
    entry = rec["entry"]
    month = int(q.data.split(":", 1)[1])
    date = make_date(rec["day"], month, rec["year"])
    if date is None:
        hint = f"⚠️ {rec['day']} {MONTH_NAMES_ID[month]} isn't a real date. Pick another month:"
        await _edit_form(context, _change_field_text(entry, hint), month_kb())
        return CHANGE_DATE_MONTH
    return await _apply_change(
        context, date=date, label="📅 Date",
        old=format_date_id(entry["date"]), new=format_date_id(date),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Delete flow
# ─────────────────────────────────────────────────────────────────────────────
async def _delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rec"] = {}
    await _show_form(update, context, _id_prompt("🗑️ <b>Delete an entry</b>"), cancel_kb())
    return DELETE_ID


async def delete_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not text.isdigit():
        await _edit_form(context, _id_prompt("🗑️ <b>Delete an entry</b>", "⚠️ Send a numeric ID."), cancel_kb())
        return DELETE_ID
    entry = _db(context).get_expense_by_id(int(text))
    if entry is None:
        await _edit_form(
            context,
            _id_prompt("🗑️ <b>Delete an entry</b>", f"❌ No entry with ID <code>{esc(text)}</code>."),
            cancel_kb(),
        )
        return DELETE_ID
    _rec(context)["entry"] = entry
    await _edit_form(context, "🗑️ <b>Delete this entry?</b>\n\n" + render_entry_card(entry), confirm_kb("delete"))
    return DELETE_CONFIRM


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    entry = _rec(context)["entry"]
    try:
        _db(context).delete_expense(entry["id"])
    except Exception as e:
        logger.exception("Flow /delete failed: %s", e)
        await _edit_form(context, "❌ Something went wrong. Please try again.", menu_button_kb())
        return _end(context)
    await _edit_form(context, render_deleted(entry), menu_button_kb())
    logger.info("Flow deleted expense id=%s", entry["id"])
    return _end(context)


# ─────────────────────────────────────────────────────────────────────────────
# Cancel / fallbacks
# ─────────────────────────────────────────────────────────────────────────────
async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancelled.", parse_mode=ParseMode.HTML, reply_markup=main_menu_kb()
    )
    return ConversationHandler.END


async def cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    try:
        await q.edit_message_text("❌ Cancelled.", parse_mode=ParseMode.HTML, reply_markup=menu_button_kb())
    except BadRequest:
        pass
    return ConversationHandler.END


async def stale_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Acknowledge a tap that doesn't belong to the current step (returns None → state unchanged)."""
    await update.callback_query.answer("That step is done — use the buttons shown, or /cancel.")


async def stale_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Please use the buttons above, or send /cancel.")


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────
def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", add_entry),
            CommandHandler("check", check_entry),
            CommandHandler("audit", audit_entry),
            CommandHandler("change", change_entry),
            CommandHandler("delete", delete_entry),
            CallbackQueryHandler(menu_router, pattern=r"^menu:(add|check|audit|change|delete)$"),
        ],
        states={
            ADD_DAY: [CallbackQueryHandler(add_day, pattern=r"^day:")],
            ADD_MONTH: [CallbackQueryHandler(add_month, pattern=r"^mon:")],
            ADD_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_notes)],
            ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_amount)],
            ADD_BANK: [CallbackQueryHandler(add_bank, pattern=r"^bank:")],
            ADD_CONFIRM: [CallbackQueryHandler(add_submit, pattern=r"^ok:submit$")],
            CHECK_DAY: [CallbackQueryHandler(check_day, pattern=r"^day:")],
            CHECK_MONTH: [CallbackQueryHandler(check_month, pattern=r"^mon:")],
            CHECK_YEAR: [CallbackQueryHandler(check_year, pattern=r"^yr:")],
            CHECK_BANK: [CallbackQueryHandler(check_bank, pattern=r"^bank:")],
            AUDIT_MONTH: [CallbackQueryHandler(audit_month_pick, pattern=r"^mon:")],
            AUDIT_YEAR: [CallbackQueryHandler(audit_year_pick, pattern=r"^yr:")],
            CHANGE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_id)],
            CHANGE_FIELD: [CallbackQueryHandler(change_field, pattern=r"^fld:")],
            CHANGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_amount)],
            CHANGE_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_notes)],
            CHANGE_BANK: [CallbackQueryHandler(change_bank, pattern=r"^bank:")],
            CHANGE_DATE_DAY: [CallbackQueryHandler(change_date_day, pattern=r"^day:")],
            CHANGE_DATE_MONTH: [CallbackQueryHandler(change_date_month, pattern=r"^mon:")],
            DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_id)],
            DELETE_CONFIRM: [CallbackQueryHandler(delete_confirm, pattern=r"^ok:delete$")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_cmd),
            CallbackQueryHandler(cancel_cb, pattern=r"^cancel$"),
            CallbackQueryHandler(stale_cb),
            MessageHandler(filters.TEXT & ~filters.COMMAND, stale_text),
        ],
        name="expense_wizard",
        allow_reentry=True,
    )
