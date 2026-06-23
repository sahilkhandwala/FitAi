# main.py

## Summary
Bot entry point. Builds a python-telegram-bot Application, registers all handlers in correct priority order, sets up an Uptime Kuma heartbeat job (every 5 minutes), and runs polling. DB session is created here and will be passed to init_tools() once Wave 2 agent infrastructure is implemented.

## Functions
- heartbeat(context) — async job callback: pings UPTIME_KUMA_PUSH_URL via aiohttp if set; failure is silent
- create_application() — creates DB engine + session, builds Application, registers all handlers and the heartbeat job; returns Application

## Non-function code
- `if __name__ == "__main__"`: logging.basicConfig + create_application().run_polling()
- `# from bot.agents.tool_registry import init_tools` — commented out until Wave 2

## Imports
- aiohttp — async HTTP for Uptime Kuma heartbeat
- telegram.ext — Application, handlers, filters
- bot.handlers.commands — handle_profile_command, handle_help_command, handle_addfood_command, handle_text_message
- bot.handlers.health — handle_document
- bot.handlers.meal — handle_photo, handle_meal_type_callback
- config — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UPTIME_KUMA_PUSH_URL
- db — get_engine, get_session_factory

## Imported by
- (entry point — nothing imports this)

## Tags
telegram, entrypoint, bot, handlers, heartbeat

## Node path
bot/main.py
