from __future__ import annotations
import logging
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from database import Database
from config import BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()

INDONESIAN_MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12
}

MONTH_NAMES = {v: k.capitalize() for k, v in INDONESIAN_MONTHS.items()}

def parse_indonesian_date(date_str: str) -> datetime | None:
    """Parse date like '8 Maret 2026' into datetime."""
    parts = date_str.strip().split()
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        month = INDONESIAN_MONTHS.get(parts[1].lower())
        year = int(parts[2])
        if not month:
            return None
        return datetime(year, month, day)
    except (ValueError, IndexError):
        return None


def format_rupiah(amount: int) -> str:
    return f"Rp {amount:,}".replace(",", ".")


async def handle_expense_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text expense input: '8 Maret 2026 25000 Makan'"""
    text = update.message.text.strip()

    # Skip if it looks like a command
    if text.startswith("/"):
        return

    # Expected: <day> <month> <year> <amount> <notes...>
    pattern = r"^(\d+)\s+(\w+)\s+(\d{4})\s+(\d+)\s+(.+)$"
    match = re.match(pattern, text, re.IGNORECASE)

    if not match:
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "📌 Correct format:\n"
            "`<day> <month> <year> <amount> <notes>`\n\n"
            "✅ Example:\n"
            "`8 Maret 2026 25000 Makan siang`\n"
            "`15 April 2026 50000 Transportasi`",
            parse_mode="Markdown"
        )
        return

    day_str, month_str, year_str, amount_str, notes = match.groups()
    date_str = f"{day_str} {month_str} {year_str}"
    date = parse_indonesian_date(date_str)

    if not date:
        await update.message.reply_text(
            "❌ *Invalid date!*\n\n"
            "📌 Use Indonesian month names:\n"
            "`Januari, Februari, Maret, April, Mei, Juni,`\n"
            "`Juli, Agustus, September, Oktober, November, Desember`\n\n"
            "✅ Example: `8 Maret 2026 25000 Makan`",
            parse_mode="Markdown"
        )
        return

    amount = int(amount_str)
    db.add_expense(date, amount, notes.strip())

    await update.message.reply_text(
        f"✅ *Expense saved!*\n\n"
        f"📅 Date: {date.strftime('%d %B %Y')}\n"
        f"💰 Amount: {format_rupiah(amount)}\n"
        f"📝 Notes: {notes.strip()}",
        parse_mode="Markdown"
    )


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/tanggal <day> <month> <year> - Get expenses for a specific date."""
    args = context.args

    if len(args) != 3:
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "📌 Correct format:\n"
            "`/tanggal <day> <month> <year>`\n\n"
            "✅ Example:\n"
            "`/tanggal 8 Maret 2026`",
            parse_mode="Markdown"
        )
        return

    date = parse_indonesian_date(" ".join(args))
    if not date:
        await update.message.reply_text(
            "❌ *Invalid date!*\n\n"
            "📌 Use Indonesian month names:\n"
            "`Januari, Februari, Maret, April, Mei, Juni,`\n"
            "`Juli, Agustus, September, Oktober, November, Desember`\n\n"
            "✅ Example: `/tanggal 8 Maret 2026`",
            parse_mode="Markdown"
        )
        return

    expenses = db.get_expenses_by_date(date)

    if not expenses:
        await update.message.reply_text(
            f"📭 No expenses found for *{date.strftime('%d %B %Y')}*.",
            parse_mode="Markdown"
        )
        return

    total = sum(e["amount"] for e in expenses)
    lines = [f"📅 *Expenses on {date.strftime('%d %B %Y')}*\n"]
    for e in expenses:
        lines.append(f"• `[ID:{e['id']}]` {format_rupiah(e['amount'])} — {e['notes']}")
    lines.append(f"\n💰 *Total: {format_rupiah(total)}*")
    lines.append(f"\n_Use `/delete <id>` or `/edit <id> <amount> <notes>` to manage entries._")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def get_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/range <day> <month> <year> <day> <month> <year> [detail]"""
    args = context.args
    show_detail = False

    if len(args) in (6, 7):
        if len(args) == 7 and args[6].lower() == "detail":
            show_detail = True
            args = args[:6]
        elif len(args) == 7:
            await update.message.reply_text(
                "❌ *Invalid format!*\n\n"
                "📌 Correct format:\n"
                "`/range <start_day> <start_month> <start_year> <end_day> <end_month> <end_year> [detail]`\n\n"
                "✅ Examples:\n"
                "`/range 1 Maret 2026 31 Maret 2026`\n"
                "`/range 1 Maret 2026 31 Maret 2026 detail`",
                parse_mode="Markdown"
            )
            return
    else:
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "📌 Correct format:\n"
            "`/range <start_day> <start_month> <start_year> <end_day> <end_month> <end_year> [detail]`\n\n"
            "✅ Examples:\n"
            "`/range 1 Maret 2026 31 Maret 2026`\n"
            "`/range 1 Maret 2026 31 Maret 2026 detail`",
            parse_mode="Markdown"
        )
        return

    start_date = parse_indonesian_date(" ".join(args[:3]))
    end_date = parse_indonesian_date(" ".join(args[3:6]))

    if not start_date or not end_date:
        await update.message.reply_text(
            "❌ *Invalid date(s)!*\n\n"
            "📌 Use Indonesian month names:\n"
            "`Januari, Februari, Maret, April, Mei, Juni,`\n"
            "`Juli, Agustus, September, Oktober, November, Desember`",
            parse_mode="Markdown"
        )
        return

    if start_date > end_date:
        await update.message.reply_text(
            "❌ Start date must be *before or equal* to end date.",
            parse_mode="Markdown"
        )
        return

    expenses = db.get_expenses_by_range(start_date, end_date)

    if not expenses:
        await update.message.reply_text(
            f"📭 No expenses found between "
            f"*{start_date.strftime('%d %B %Y')}* and *{end_date.strftime('%d %B %Y')}*.",
            parse_mode="Markdown"
        )
        return

    total = sum(e["amount"] for e in expenses)
    lines = [
        f"📆 *Expenses: {start_date.strftime('%d %B %Y')} → {end_date.strftime('%d %B %Y')}*\n"
    ]

    if show_detail:
        for e in expenses:
            date_label = e["date"].strftime("%d %b")
            lines.append(f"• `[ID:{e['id']}]` [{date_label}] {format_rupiah(e['amount'])} — {e['notes']}")
        lines.append(f"\n💰 *Total: {format_rupiah(total)}*")
        lines.append(f"\n_Use `/delete <id>` or `/edit <id> <amount> <notes>` to manage entries._")
    else:
        lines.append(f"📊 Total entries: {len(expenses)}")
        lines.append(f"💰 *Total: {format_rupiah(total)}*")
        lines.append(f"\n_Tip: Add `detail` at the end to see all entries with IDs._")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/summary <month> or /summary <month1> <month2>"""
    args = context.args

    if len(args) not in (1, 2):
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "📌 Correct format:\n"
            "`/summary <month>` — single month\n"
            "`/summary <month1> <month2>` — month range\n\n"
            "✅ Examples:\n"
            "`/summary Maret`\n"
            "`/summary Maret April`",
            parse_mode="Markdown"
        )
        return

    current_year = datetime.now().year

    month1_num = INDONESIAN_MONTHS.get(args[0].lower())
    if not month1_num:
        await update.message.reply_text(
            f"❌ *'{args[0]}' is not a valid month.*\n\n"
            "📌 Use Indonesian month names:\n"
            "`Januari, Februari, Maret, April, Mei, Juni,`\n"
            "`Juli, Agustus, September, Oktober, November, Desember`",
            parse_mode="Markdown"
        )
        return

    if len(args) == 1:
        # Single month
        data = db.get_summary_by_months(month1_num, month1_num, current_year)
        month_name = MONTH_NAMES[month1_num]

        if not data or data[0]["total"] == 0:
            await update.message.reply_text(
                f"📭 No expenses found for *{month_name} {current_year}*.",
                parse_mode="Markdown"
            )
            return

        row = data[0]
        lines = [
            f"📊 *Summary — {month_name} {current_year}*\n",
            f"📝 Total entries: {row['count']}",
            f"💰 Total: {format_rupiah(row['total'])}",
        ]
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    else:
        # Month range
        month2_num = INDONESIAN_MONTHS.get(args[1].lower())
        if not month2_num:
            await update.message.reply_text(
                f"❌ *'{args[1]}' is not a valid month.*\n\n"
                "📌 Use Indonesian month names:\n"
                "`Januari, Februari, Maret, April, Mei, Juni,`\n"
                "`Juli, Agustus, September, Oktober, November, Desember`",
                parse_mode="Markdown"
            )
            return

        if month1_num > month2_num:
            await update.message.reply_text(
                f"❌ *{MONTH_NAMES[month1_num]}* must come before *{MONTH_NAMES[month2_num]}*.",
                parse_mode="Markdown"
            )
            return

        data = db.get_summary_by_months(month1_num, month2_num, current_year)

        if not data:
            await update.message.reply_text(
                f"📭 No expenses found from *{MONTH_NAMES[month1_num]}* to *{MONTH_NAMES[month2_num]} {current_year}*.",
                parse_mode="Markdown"
            )
            return

        lines = [
            f"📊 *Summary — {MONTH_NAMES[month1_num]} to {MONTH_NAMES[month2_num]} {current_year}*\n"
        ]

        grand_total = 0
        for row in data:
            month_name = MONTH_NAMES[row["month"]]
            lines.append(f"📅 *{month_name}*")
            lines.append(f"   📝 Entries: {row['count']}")
            lines.append(f"   💰 Total: {format_rupiah(row['total'])}\n")
            grand_total += row["total"]

        lines.append(f"🧾 *Grand Total: {format_rupiah(grand_total)}*")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        
async def delete_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "📌 Correct format:\n"
            "`/delete <id>`\n\n"
            "✅ Example: `/delete 5`\n\n"
            "_Use `/tanggal` or `/range ... detail` to find the ID._",
            parse_mode="Markdown"
        )
        return
    expense_id = int(args[0])
    expense = db.get_expense_by_id(expense_id)
    if not expense:
        await update.message.reply_text(f"❌ No expense found with *ID {expense_id}*.", parse_mode="Markdown")
        return
    db.delete_expense(expense_id)
    await update.message.reply_text(
        f"🗑️ *Expense deleted!*\n\n"
        f"📅 Date: {expense['date'].strftime('%d %B %Y')}\n"
        f"💰 Amount: {format_rupiah(expense['amount'])}\n"
        f"📝 Notes: {expense['notes']}",
        parse_mode="Markdown"
    )


async def edit_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3 or not args[0].isdigit() or not args[1].isdigit():
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "📌 Correct format:\n"
            "`/edit <id> <amount> <notes>`\n\n"
            "✅ Example: `/edit 5 30000 Makan malam`\n\n"
            "_Use `/tanggal` or `/range ... detail` to find the ID._",
            parse_mode="Markdown"
        )
        return
    expense_id = int(args[0])
    new_amount = int(args[1])
    new_notes = " ".join(args[2:])
    expense = db.get_expense_by_id(expense_id)
    if not expense:
        await update.message.reply_text(f"❌ No expense found with *ID {expense_id}*.", parse_mode="Markdown")
        return
    db.edit_expense(expense_id, new_amount, new_notes)
    await update.message.reply_text(
        f"✏️ *Expense updated!*\n\n"
        f"📅 Date: {expense['date'].strftime('%d %B %Y')}\n"
        f"💰 Amount: {format_rupiah(expense['amount'])} → {format_rupiah(new_amount)}\n"
        f"📝 Notes: {expense['notes']} → {new_notes}",
        parse_mode="Markdown"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to your Expense Tracker!*\n\n"
        "📌 *How to log an expense:*\n"
        "`<day> <month> <year> <amount> <notes>`\n"
        "Example: `8 Maret 2026 25000 Makan siang`\n\n"
        "📌 *Commands:*\n"
        "`/tanggal <day> <month> <year>` — expenses on a date\n"
        "`/range <start> <end> [detail]` — expenses in a date range\n"
        "`/summary <month>` — monthly summary\n"
        "`/summary <month1> <month2>` — multi-month summary\n"
        "`/help` — show this message",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tanggal", get_date))
    app.add_handler(CommandHandler("range", get_range))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("delete", delete_expense))
    app.add_handler(CommandHandler("edit", edit_expense))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense_input))

    logger.info("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()