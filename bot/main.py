"""Entry point — registers all handlers and starts the bot."""

from __future__ import annotations

import logging

import aiohttp
from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.handlers.commands import (
    handle_addfood_command,
    handle_help_command,
    handle_profile_command,
    handle_text_message,
)
from bot.handlers.health import handle_document
from bot.handlers.meal import handle_meal_type_callback, handle_photo
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UPTIME_KUMA_PUSH_URL
from db import get_engine, get_session_factory

# Uncomment when bot/agents/tool_registry.py is implemented (Wave 2):
# from bot.agents.tool_registry import init_tools

logger = logging.getLogger(__name__)


async def heartbeat(context) -> None:
    """Ping Uptime Kuma push monitor every 5 minutes."""
    if UPTIME_KUMA_PUSH_URL:
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(UPTIME_KUMA_PUSH_URL)
        except Exception:
            pass  # heartbeat failure is not fatal


def create_application() -> Application:
    engine = get_engine()
    session_factory = get_session_factory(engine)
    session = session_factory()

    # Wire up tools with the DB session — uncomment when tool_registry is implemented:
    # init_tools(session)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers (order matters — more specific first)
    app.add_handler(CommandHandler("profile", handle_profile_command))
    app.add_handler(CommandHandler("help", handle_help_command))
    app.add_handler(CommandHandler("addfood", handle_addfood_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(handle_meal_type_callback))

    # Uptime Kuma heartbeat — every 5 minutes, first ping after 10s
    app.job_queue.run_repeating(heartbeat, interval=300, first=10)

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_application()
    app.run_polling()
