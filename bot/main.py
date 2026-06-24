"""Entry point — registers all handlers and starts the bot."""

from __future__ import annotations

import asyncio
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
from bot.handlers.health import handle_document, handle_labconfirm_callback
from bot.handlers.meal import handle_meal_type_callback, handle_photo
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UPTIME_KUMA_PUSH_URL
from db import get_engine, get_session_factory

logger = logging.getLogger(__name__)


async def heartbeat(context) -> None:
    """Ping Uptime Kuma push monitor every 5 minutes."""
    if UPTIME_KUMA_PUSH_URL:
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(UPTIME_KUMA_PUSH_URL)
        except Exception:
            pass


async def post_init(application: Application) -> None:
    """
    Called by python-telegram-bot after the Application is fully built.
    Wire the DB session, main event loop, and Telegram app into tool_registry,
    then build the AGENT_REGISTRY so all agents are ready before the first message.
    """
    from bot.agents.tool_registry import init_tools, init_bot
    from bot.agents.agent_loader import AGENT_REGISTRY, build_agent_registry

    engine = get_engine()
    session = get_session_factory(engine)()

    loop = asyncio.get_running_loop()
    init_tools(session, main_loop=loop)
    init_bot(application)
    AGENT_REGISTRY.update(build_agent_registry())
    logger.info("Agent registry built: %s", list(AGENT_REGISTRY.keys()))


def create_application() -> Application:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("profile", handle_profile_command))
    app.add_handler(CommandHandler("help", handle_help_command))
    app.add_handler(CommandHandler("addfood", handle_addfood_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(handle_meal_type_callback, pattern="^meal_type:"))
    app.add_handler(CallbackQueryHandler(handle_labconfirm_callback, pattern="^labconfirm:"))

    app.job_queue.run_repeating(heartbeat, interval=300, first=10)

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_application()
    app.run_polling()
