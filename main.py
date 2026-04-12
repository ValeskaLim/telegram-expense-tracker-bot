from __future__ import annotations
import logging
import re
from datetime import datetime
from typing import Optional
from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)
from database import Database
from config import BOT_TOKEN

# ─────────────────────────────────────────────────────────────────────────────
# Configuration & Constants
# ─────────────────────────────────────────────────────────────────────────────

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
MONTH_LIST_ENG = ", ".join([f"`{m.capitalize()}`" for m in INDONESIAN_MONTHS.keys()])

# Validation constants
MAX_AMOUNT = 1_000_000_000  # 1 billion rupiah
MIN_AMOUNT = 1

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def parse_indonesian_date(date_str: str) -> Optional[datetime]:
    """Parse date like '8 Maret 2026' into datetime."""
    parts = date_str.strip().split()
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        month = INDONESIAN_MONTHS.get(parts[1].lower())
        year = int(parts[2])
        if not month or not (1 <= day <= 31):
            return None
        return datetime(year, month, day)
    except (ValueError, IndexError):
        return None


def format_rupiah(amount: int) -> str:
    """Format amount as Indonesian Rupiah."""
    return f"Rp {amount:,}".replace(",", ".")


def get_month_names_help() -> str:
    """Get formatted month names for help messages."""
    return (
        "`Januari, Februari, Maret, April, Mei, Juni,`\n"
        "`Juli, Agustus, September, Oktober, November, Desember`"
    )


async def send_error_message(update: Update, message: str):
    """Send a formatted error message."""
    await update.message.reply_text(f"❌ *{message}*", parse_mode="Markdown")


async def send_success_message(update: Update, message: str):
    """Send a formatted success message."""
    await update.message.reply_text(f"✅ *{message}*", parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────────────────────────────────────────

async def handle_expense_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle natural language expense input."""
    text = update.message.text.strip()

    if text.startswith("/"):
        return

    try:
        # Extract optional [category:...]
        category = 'general'
        category_match = re.search(r'\[category:(\w+)\]', text, re.IGNORECASE)
        if category_match:
            category = category_match.group(1).lower()
            text = text[:category_match.start()].strip()

        pattern = r"^(\d+)\s+(\w+)\s+(\d{4})\s+(\d+)\s+(.+)$"
        match = re.match(pattern, text, re.IGNORECASE)

        if not match:
            await update.message.reply_text(
                "❌ *Invalid format!*\n\n"
                "📌 *Correct format:*\n"
                "`<day> <month> <year> <amount> <notes> [category:name]`\n\n"
                "✅ *Examples:*\n"
                "`8 Maret 2026 25000 Makan siang`\n"
                "`8 Maret 2026 25000 Makan siang [category:food]`",
                parse_mode="Markdown"
            )
            return

        day_str, month_str, year_str, amount_str, notes = match.groups()
        date_str = f"{day_str} {month_str} {year_str}"
        date = parse_indonesian_date(date_str)

        if not date:
            await update.message.reply_text(
                "❌ *Invalid date!*\n\n"
                "📌 *Use Indonesian month names:*\n"
                f"{get_month_names_help()}\n\n"
                "✅ *Example:* `8 Maret 2026 25000 Makan [category:food]`",
                parse_mode="Markdown"
            )
            return

        amount = int(amount_str)
        
        # Validate amount
        if amount < MIN_AMOUNT:
            await send_error_message(update, "Amount must be at least Rp 1")
            return
        if amount > MAX_AMOUNT:
            await send_error_message(update, f"Amount exceeds maximum (Rp {MAX_AMOUNT:,})")
            return

        expense_id = db.add_expense(date, amount, notes.strip(), category)

        await update.message.reply_text(
            f"✅ *Expense saved!*\n\n"
            f"📅 Date: {date.strftime('%d %B %Y')}\n"
            f"💰 Amount: {format_rupiah(amount)}\n"
            f"📝 Notes: {notes.strip()}\n"
            f"🏷️ Category: {category}\n"
            f"🔖 ID: `{expense_id}`",
            parse_mode="Markdown"
        )
        logger.info(f"User added expense: ID={expense_id}, amount={amount}, category={category}")
        
    except Exception as e:
        logger.error(f"Error handling expense input: {e}")
        await send_error_message(update, "Something went wrong. Please try again.")


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/tanggal <day> <month> <year> [category] - Get expenses for a specific date."""
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "📌 *Correct format:*\n"
            "`/tanggal <day> <month> <year> [category]`\n\n"
            "✅ *Example:*\n"
            "`/tanggal 8 Maret 2026` or `/tanggal 8 Maret 2026 bill`",
            parse_mode="Markdown"
        )
        return

    try:
        date = parse_indonesian_date(" ".join(args[:3]))
        if not date:
            await update.message.reply_text(
                "❌ *Invalid date!*\n\n"
                "📌 *Use Indonesian month names:*\n"
                f"{get_month_names_help()}\n\n"
                "✅ *Example:* `/tanggal 8 Maret 2026`",
                parse_mode="Markdown"
            )
            return

        category = args[3] if len(args) > 3 else None
        expenses = db.get_expenses_by_date(date, category)

        if not expenses:
            category_text = f" in category *{category}*" if category else ""
            await update.message.reply_text(
                f"📭 No expenses found for *{date.strftime('%d %B %Y')}*{category_text}.",
                parse_mode="Markdown"
            )
            return

        total = sum(e["amount"] for e in expenses)
        lines = [f"📅 *Expenses on {date.strftime('%d %B %Y')}*\n"]
        for e in expenses:
            lines.append(
                f"• `[ID:{e['id']}]` {format_rupiah(e['amount'])} — {e['notes']} 🏷️ {e['category']}"
            )
        lines.append(f"\n💰 *Total: {format_rupiah(total)}*")
        lines.append(f"\n_Use `/delete <id>` or `/edit <id> ...` to manage entries._")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        logger.info(f"User queried expenses for date: {date.strftime('%Y-%m-%d')}")
        
    except Exception as e:
        logger.error(f"Error in /tanggal: {e}")
        await send_error_message(update, "Something went wrong. Please try again.")


async def get_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/range <start_day> <start_month> <start_year> <end_day> <end_month> <end_year> [detail]"""
    args = context.args
    show_detail = False

    try:
        if len(args) not in (6, 7):
            await update.message.reply_text(
                "❌ *Invalid format!*\n\n"
                "📌 *Correct format:*\n"
                "`/range <start_day> <start_month> <start_year> <end_day> <end_month> <end_year> [detail]`\n\n"
                "✅ *Examples:*\n"
                "`/range 1 Maret 2026 31 Maret 2026`\n"
                "`/range 1 Maret 2026 31 Maret 2026 detail`",
                parse_mode="Markdown"
            )
            return

        if len(args) == 7:
            if args[6].lower() == "detail":
                show_detail = True
            else:
                await update.message.reply_text(
                    "❌ *Invalid option!*\n\n"
                    "The 7th argument must be `detail` or omitted.\n\n"
                    "✅ *Examples:*\n"
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
                "📌 *Use Indonesian month names:*\n"
                f"{get_month_names_help()}",
                parse_mode="Markdown"
            )
            return

        if start_date > end_date:
            await send_error_message(update, "Start date must be before or equal to end date.")
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
                lines.append(
                    f"• `[ID:{e['id']}]` [{date_label}] {format_rupiah(e['amount'])} — {e['notes']} 🏷️ {e['category']}"
                )
            lines.append(f"\n💰 *Total: {format_rupiah(total)}*")
            lines.append(f"\n_Use `/delete <id>` or `/edit <id> ...` to manage entries._")
        else:
            lines.append(f"📊 Total entries: {len(expenses)}")
            lines.append(f"💰 *Total: {format_rupiah(total)}*")
            lines.append(f"\n_Tip: Add `detail` at the end to see all entries with IDs._")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        logger.info(f"User queried expenses for range: {start_date.date()} to {end_date.date()}")
        
    except Exception as e:
        logger.error(f"Error in /range: {e}")
        await send_error_message(update, "Something went wrong. Please try again.")


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/summary <month> [category] or /summary <month1> <month2> [category]"""
    args = context.args

    try:
        if len(args) not in (1, 2, 3):
            await update.message.reply_text(
                "❌ *Invalid format!*\n\n"
                "📌 *Correct format:*\n"
                "`/summary <month> [category]` — single month\n"
                "`/summary <month1> <month2> [category]` — month range\n\n"
                "✅ *Examples:*\n"
                "`/summary Maret`\n"
                "`/summary Maret food`\n"
                "`/summary Maret April`\n"
                "`/summary Maret April bill`",
                parse_mode="Markdown"
            )
            return

        current_year = datetime.now().year
        
        # Determine if category is provided (last arg if not a valid month)
        category = None
        months_to_process = args
        
        if len(args) >= 2:
            potential_category = args[-1].lower()
            if potential_category not in INDONESIAN_MONTHS:
                category = potential_category
                months_to_process = args[:-1]

        if len(months_to_process) == 1:
            # Single month
            month1_num = INDONESIAN_MONTHS.get(months_to_process[0].lower())
            if not month1_num:
                await update.message.reply_text(
                    f"❌ *'{months_to_process[0]}' is not a valid month.*\n\n"
                    "📌 *Use Indonesian month names:*\n"
                    f"{get_month_names_help()}",
                    parse_mode="Markdown"
                )
                return

            data = db.get_summary_by_months(month1_num, month1_num, current_year, category)
            month_name = MONTH_NAMES[month1_num]

            if not data or data[0]["total"] == 0:
                category_text = f" in category *{category}*" if category else ""
                await update.message.reply_text(
                    f"📭 No expenses found for *{month_name} {current_year}*{category_text}.",
                    parse_mode="Markdown"
                )
                return

            row = data[0]
            lines = [
                f"📊 *Summary — {month_name} {current_year}*\n",
                f"📝 Total entries: {row['count']}",
                f"💰 Total: {format_rupiah(row['total'])}",
            ]
            if category:
                lines.append(f"🏷️ Category: {category}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        else:
            # Month range
            month1_num = INDONESIAN_MONTHS.get(months_to_process[0].lower())
            month2_num = INDONESIAN_MONTHS.get(months_to_process[1].lower())
            
            if not month1_num:
                await update.message.reply_text(
                    f"❌ *'{months_to_process[0]}' is not a valid month.*\n\n"
                    "📌 *Use Indonesian month names:*\n"
                    f"{get_month_names_help()}",
                    parse_mode="Markdown"
                )
                return
                
            if not month2_num:
                await update.message.reply_text(
                    f"❌ *'{months_to_process[1]}' is not a valid month.*\n\n"
                    "📌 *Use Indonesian month names:*\n"
                    f"{get_month_names_help()}",
                    parse_mode="Markdown"
                )
                return

            if month1_num > month2_num:
                await send_error_message(
                    update, 
                    f"*{MONTH_NAMES[month1_num]}* must come before *{MONTH_NAMES[month2_num]}*."
                )
                return

            data = db.get_summary_by_months(month1_num, month2_num, current_year, category)

            if not data:
                category_text = f" in category *{category}*" if category else ""
                await update.message.reply_text(
                    f"📭 No expenses found from *{MONTH_NAMES[month1_num]}* to "
                    f"*{MONTH_NAMES[month2_num]} {current_year}*{category_text}.",
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
            if category:
                lines.append(f"🏷️ Category: {category}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        logger.info(f"User queried summary for months: {months_to_process}")
        
    except Exception as e:
        logger.error(f"Error in /summary: {e}")
        await send_error_message(update, "Something went wrong. Please try again.")


async def delete_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/delete <id> - Delete an expense by ID."""
    args = context.args
    
    try:
        if len(args) != 1 or not args[0].isdigit():
            await update.message.reply_text(
                "❌ *Invalid format!*\n\n"
                "📌 *Correct format:*\n"
                "`/delete <id>`\n\n"
                "✅ *Example:* `/delete 5`\n\n"
                "_Use `/tanggal` or `/range ... detail` to find the ID._",
                parse_mode="Markdown"
            )
            return
            
        expense_id = int(args[0])
        expense = db.get_expense_by_id(expense_id)
        
        if not expense:
            await send_error_message(update, f"No expense found with *ID {expense_id}*.")
            return
            
        db.delete_expense(expense_id)
        
        await update.message.reply_text(
            f"🗑️ *Expense deleted!*\n\n"
            f"📅 Date: {expense['date'].strftime('%d %B %Y')}\n"
            f"💰 Amount: {format_rupiah(expense['amount'])}\n"
            f"📝 Notes: {expense['notes']}\n"
            f"🏷️ Category: {expense['category']}",
            parse_mode="Markdown"
        )
        logger.info(f"User deleted expense ID: {expense_id}")
        
    except Exception as e:
        logger.error(f"Error in /delete: {e}")
        await send_error_message(update, "Something went wrong. Please try again.")


async def edit_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/edit <id> <amount> <notes> [category:name] - Edit an expense."""
    args = context.args
    
    try:
        if len(args) < 3 or not args[0].isdigit() or not args[1].isdigit():
            await update.message.reply_text(
                "❌ *Invalid format!*\n\n"
                "📌 *Correct format:*\n"
                "`/edit <id> <amount> <notes> [category:name]`\n\n"
                "✅ *Example:* `/edit 5 30000 Makan malam [category:food]`\n\n"
                "_Use `/tanggal` or `/range ... detail` to find the ID._",
                parse_mode="Markdown"
            )
            return
            
        expense_id = int(args[0])
        new_amount = int(args[1])
        
        # Check for category in notes
        category = None
        notes_with_category = " ".join(args[2:])
        category_match = re.search(r'\[category:(\w+)\]', notes_with_category, re.IGNORECASE)
        
        if category_match:
            category = category_match.group(1).lower()
            new_notes = notes_with_category[:category_match.start()].strip()
        else:
            new_notes = notes_with_category
        
        # Validate amount
        if new_amount < MIN_AMOUNT:
            await send_error_message(update, "Amount must be at least Rp 1")
            return
        if new_amount > MAX_AMOUNT:
            await send_error_message(update, f"Amount exceeds maximum (Rp {MAX_AMOUNT:,})")
            return
        
        expense = db.get_expense_by_id(expense_id)
        if not expense:
            await send_error_message(update, f"No expense found with *ID {expense_id}*.")
            return
            
        db.edit_expense(expense_id, new_amount=new_amount, new_notes=new_notes, new_category=category)
        
        # Build response showing what changed
        changes = []
        if expense['amount'] != new_amount:
            changes.append(f"💰 Amount: {format_rupiah(expense['amount'])} → {format_rupiah(new_amount)}")
        if expense['notes'] != new_notes:
            changes.append(f"📝 Notes: {expense['notes']} → {new_notes}")
        if category and expense['category'] != category:
            changes.append(f"🏷️ Category: {expense['category']} → {category}")
        
        await update.message.reply_text(
            f"✏️ *Expense updated!*\n\n"
            f"📅 Date: {expense['date'].strftime('%d %B %Y')}\n"
            + "\n".join(changes) if changes else "ℹ️ No changes made.",
            parse_mode="Markdown"
        )
        logger.info(f"User edited expense ID: {expense_id}")
        
    except Exception as e:
        logger.error(f"Error in /edit: {e}")
        await send_error_message(update, "Something went wrong. Please try again.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message and usage guide."""
    await update.message.reply_text(
        "👋 *Welcome to your Expense Tracker!*\n\n"
        "📌 *How to log an expense:*\n"
        "Just send a message in this format:\n"
        "`<day> <month> <year> <amount> <notes> [category:name]`\n\n"
        "✅ *Example:*\n"
        "`8 Maret 2026 25000 Makan siang [category:food]`\n\n"
        "📌 *Commands:*\n"
        "`/tanggal <day> <month> <year> [category]` — expenses on a date\n"
        "`/range <start> <end> [detail]` — expenses in a date range\n"
        "`/summary <month> [category]` — monthly summary\n"
        "`/summary <month1> <month2> [category]` — multi-month summary\n"
        "`/edit <id> <amount> <notes> [category:name]` — edit an expense\n"
        "`/delete <id>` — delete an expense\n"
        "`/help` — show this message",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message."""
    await start(update, context)


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Initialize and run the bot."""
    logger.info("Starting Expense Tracker Bot...")
    
    app = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tanggal", get_date))
    app.add_handler(CommandHandler("range", get_range))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("delete", delete_expense))
    app.add_handler(CommandHandler("edit", edit_expense))
    
    # Message handler for expense input (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense_input))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
