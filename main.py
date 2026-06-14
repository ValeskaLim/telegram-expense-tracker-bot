"""Entry point: wires the Telegram handlers to the bot and starts polling."""
from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

import handlers
from config import BOT_TOKEN
from database import Database

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    """Create the Application with the database and all handlers registered."""
    app = Application.builder().token(BOT_TOKEN).build()

    # Share a single Database instance with every handler via bot_data.
    app.bot_data["db"] = Database()

    app.add_handler(CommandHandler(["start", "help"], handlers.start))
    app.add_handler(CommandHandler("add", handlers.add_expense))
    app.add_handler(CommandHandler("check", handlers.check_date))
    app.add_handler(CommandHandler("audit", handlers.audit_month))
    app.add_handler(CommandHandler("delete", handlers.delete_expense))
    app.add_handler(CommandHandler("change", handlers.change_expense))

    # Fallbacks: unknown commands first, then any other free text.
    app.add_handler(MessageHandler(filters.COMMAND, handlers.unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.free_text))

    return app


def main() -> None:
    logger.info("Starting Expense Tracker Bot...")
    app = build_application()
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
