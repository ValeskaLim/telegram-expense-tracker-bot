"""Entry point: wires the Telegram handlers to the bot and starts polling."""
from __future__ import annotations

import logging
from datetime import time as dtime

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

import flows
import handlers
import keyboards
from config import BOT_TOKEN
from database import Database
from utils import JAKARTA_TZ

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

    # Stateless main menu / help. /start also subscribes the chat to the report.
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("menu", handlers.menu))
    app.add_handler(CommandHandler("help", handlers.help_cmd))

    # The button-driven wizard owns /add /check /audit /change /delete and the
    # menu buttons (a bare command opens the flow; a command WITH arguments runs
    # the original typed handler). Registered before the free-text fallback so
    # in-flow typing is captured by the active step.
    app.add_handler(flows.build_conversation())

    # Daily-report toggle (command + 🔔 menu button) and on-demand preview.
    app.add_handler(CommandHandler("report", handlers.report_toggle))
    app.add_handler(CommandHandler("report_now", handlers.report_now))
    app.add_handler(MessageHandler(filters.Text([keyboards.MENU_REPORT]), handlers.report_toggle))

    # Fallbacks: unknown commands first, then any other free text.
    app.add_handler(MessageHandler(filters.COMMAND, handlers.unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.free_text))

    # Schedule the nightly report at 23:00 Asia/Jakarta (needs the job-queue extra).
    if app.job_queue is not None:
        app.job_queue.run_daily(
            handlers.daily_report_job,
            time=dtime(hour=23, minute=0, tzinfo=JAKARTA_TZ),
            name="daily_report",
        )
        logger.info("Daily report scheduled for 23:00 Asia/Jakarta")
    else:
        logger.warning(
            "JobQueue unavailable — daily report disabled. "
            "Install 'python-telegram-bot[job-queue]'."
        )

    return app


def main() -> None:
    logger.info("Starting Expense Tracker Bot...")
    app = build_application()
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
