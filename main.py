"""Entry point: wires the Telegram handlers to the bot and starts polling."""
from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import flows
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

    # Stateless main menu / help.
    app.add_handler(CommandHandler(["start", "menu"], handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))

    # The button-driven wizard owns /add /check /audit /change /delete and the
    # menu:<action> buttons (a bare command opens the flow; a command WITH
    # arguments runs the original typed handler). Registered before the
    # free-text fallback so in-flow typing is captured by the active step.
    app.add_handler(flows.build_conversation())

    # 🏠 Menu / ❓ Help buttons that don't start a conversation.
    app.add_handler(CallbackQueryHandler(handlers.menu_home, pattern=r"^menu:(home|help)$"))

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
