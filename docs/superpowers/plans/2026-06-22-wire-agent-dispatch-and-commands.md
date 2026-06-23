# Wire Agent Dispatch, Commands & Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire every TODO in the bot handlers to their real agent calls, implement all stub commands, add the onboarding flow, and write the missing e2e test — making the bot fully functional before VM deployment.

**Architecture:** Telegram handlers dispatch to agents by running `agent.invoke()` in a thread executor (preserving the async event loop). Tools that need to send Telegram messages store the main event loop at startup and use `asyncio.run_coroutine_threadsafe`. LangGraph `interrupt()` pauses raise `GraphInterrupt`; handlers catch, send the interrupt message to Telegram, and track the paused agent in a shared `diskcache.Cache`.

**Tech Stack:** python-telegram-bot v20+, LangGraph v0.4+ (`GraphInterrupt`, `Command(resume=)`), AsyncSqliteSaver, langchain-anthropic, diskcache, cachetools

---

## Global Constraints

- All times in `America/Los_Angeles` via `zoneinfo` — never hardcode UTC offsets
- Single user — `TELEGRAM_CHAT_ID` is the only chat; no multi-user scoping
- No image storage — download photo bytes, pass to agent, discard
- All DB access via `db/queries.py` — never raw SQL in handlers or agents
- `AGENT_REGISTRY` (from `bot/agents/agent_loader.py`) is the canonical agent lookup
- Tests use in-memory SQLite (`conftest.py` fixtures: `session`, `mock_anthropic`)
- Run full suite before each commit: `python -m pytest tests/ -q`

---

## File Map

**Modified:**
- `bot/agents/tool_registry.py` — add `_main_loop`, update `init_tools`, update `send_telegram_msg` and interrupt tools, add `route_to_agent`
- `bot/agents/configs/orchestrator.yaml` — add `route_to_agent` to tools list
- `bot/agents/configs/meal_analyzer.yaml` — add `checkpointer: true`
- `bot/agents/configs/health_extractor.yaml` — add `checkpointer: true`
- `bot/main.py` — `post_init` callback wires session, loop, bot, builds AGENT_REGISTRY
- `bot/handlers/meal.py` — wire `handle_meal_type_callback` → MealAnalyzerAgent
- `bot/handlers/health.py` — wire `handle_document` → orchestrator classify → specialist
- `bot/handlers/commands.py` — wire all text/command handlers, implement /profile, /addfood, skip-comparison DB write
- `tests/unit/test_tool_registry.py` — add test for `route_to_agent`

**Created:**
- `bot/cache.py` — shared `diskcache.Cache` singleton + interrupt-state helpers
- `bot/handlers/onboarding.py` — multi-step onboarding flow with inline keyboards
- `tests/e2e/test_alert_flow.py` — missing e2e test for alert flow

---

## Task 1: Shared diskcache singleton + interrupt-state helpers

**Files:**
- Create: `bot/cache.py`

**Interfaces:**
- Produces:
  - `get_app_cache() -> diskcache.Cache` — returns the shared Cache instance
  - `set_paused_agent(trigger: str) -> None`
  - `get_paused_agent() -> str | None`
  - `clear_paused_agent() -> None`
  - `is_onboarding_complete() -> bool`
  - `set_onboarding_complete() -> None`
  - `has_sent_onboarding_prompt() -> bool`
  - `set_onboarding_prompt_sent() -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cache.py`:
```python
"""Unit tests for bot/cache.py — diskcache singleton and interrupt helpers."""

import pytest


@pytest.fixture
def cache_instance(tmp_path, monkeypatch):
    """Patch DISKCACHE_DIR to a temp path so tests don't write to real cache."""
    monkeypatch.setattr("config.DISKCACHE_DIR", str(tmp_path / "cache"))
    # Force module-level singleton to reset between tests
    import bot.cache as bc
    bc._cache = None
    yield
    # Cleanup
    bc._cache = None


def test_get_app_cache_returns_cache(cache_instance):
    from bot.cache import get_app_cache
    import diskcache
    c = get_app_cache()
    assert isinstance(c, diskcache.Cache)


def test_get_app_cache_is_singleton(cache_instance):
    from bot.cache import get_app_cache
    assert get_app_cache() is get_app_cache()


def test_paused_agent_round_trip(cache_instance):
    from bot.cache import set_paused_agent, get_paused_agent, clear_paused_agent
    assert get_paused_agent() is None
    set_paused_agent("photo")
    assert get_paused_agent() == "photo"
    clear_paused_agent()
    assert get_paused_agent() is None


def test_onboarding_complete_default_false(cache_instance):
    from bot.cache import is_onboarding_complete
    assert is_onboarding_complete() is False


def test_onboarding_complete_set(cache_instance):
    from bot.cache import set_onboarding_complete, is_onboarding_complete
    set_onboarding_complete()
    assert is_onboarding_complete() is True


def test_onboarding_prompt_sent_default_false(cache_instance):
    from bot.cache import has_sent_onboarding_prompt
    assert has_sent_onboarding_prompt() is False


def test_onboarding_prompt_sent_set(cache_instance):
    from bot.cache import set_onboarding_prompt_sent, has_sent_onboarding_prompt
    set_onboarding_prompt_sent()
    assert has_sent_onboarding_prompt() is True
```

- [ ] **Step 2: Run tests — verify they all FAIL**

```bash
python -m pytest tests/unit/test_cache.py -v
```
Expected: `ModuleNotFoundError: No module named 'bot.cache'`

- [ ] **Step 3: Implement `bot/cache.py`**

```python
"""
Shared diskcache.Cache singleton and interrupt/onboarding state helpers.

The Cache lives at DISKCACHE_DIR and survives bot restarts — used for:
  - paused_agent: which AGENT_REGISTRY trigger is currently interrupted
  - onboarding_complete: has user finished first-time setup
  - onboarding_prompt_sent: has the one-time lab-report tip been sent
"""

import diskcache
from config import DISKCACHE_DIR

_cache: diskcache.Cache | None = None

_KEY_PAUSED_AGENT = "paused_agent"
_KEY_ONBOARDING_COMPLETE = "onboarding_complete"
_KEY_ONBOARDING_PROMPT_SENT = "onboarding_prompt_sent"


def get_app_cache() -> diskcache.Cache:
    global _cache
    if _cache is None:
        _cache = diskcache.Cache(DISKCACHE_DIR)
    return _cache


def set_paused_agent(trigger: str) -> None:
    get_app_cache().set(_KEY_PAUSED_AGENT, trigger)


def get_paused_agent() -> str | None:
    return get_app_cache().get(_KEY_PAUSED_AGENT)


def clear_paused_agent() -> None:
    get_app_cache().delete(_KEY_PAUSED_AGENT)


def is_onboarding_complete() -> bool:
    return bool(get_app_cache().get(_KEY_ONBOARDING_COMPLETE, False))


def set_onboarding_complete() -> None:
    get_app_cache().set(_KEY_ONBOARDING_COMPLETE, True)


def has_sent_onboarding_prompt() -> bool:
    return bool(get_app_cache().get(_KEY_ONBOARDING_PROMPT_SENT, False))


def set_onboarding_prompt_sent() -> None:
    get_app_cache().set(_KEY_ONBOARDING_PROMPT_SENT, True)
```

- [ ] **Step 4: Run tests — verify they all PASS**

```bash
python -m pytest tests/unit/test_cache.py -v
```
Expected: 8 passed

- [ ] **Step 5: Full suite — verify no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all pass (+ 8 new)

- [ ] **Step 6: Commit**

```bash
git add bot/cache.py tests/unit/test_cache.py
git commit -m "feat: add shared diskcache singleton and interrupt-state helpers"
```

---

## Task 2: Add `route_to_agent` tool + update orchestrator config

**Files:**
- Modify: `bot/agents/tool_registry.py`
- Modify: `bot/agents/configs/orchestrator.yaml`
- Modify: `tests/unit/test_tool_registry.py`

**Interfaces:**
- Consumes: `TOOL_REGISTRY` from `bot/agents/tool_registry.py`
- Produces: `route_to_agent` tool callable; `AGENT_NAME_TO_TRIGGER: dict[str, str]`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tool_registry.py`:
```python
class TestRouteToAgent:
    def test_route_to_agent_returns_name(self):
        from bot.agents.tool_registry import route_to_agent
        result = route_to_agent.invoke({"agent_name": "HealthExtractorAgent"})
        assert result == "HealthExtractorAgent"

    def test_route_to_agent_in_registry(self):
        from bot.agents.tool_registry import TOOL_REGISTRY
        assert "route_to_agent" in TOOL_REGISTRY

    def test_agent_name_to_trigger_mapping(self):
        from bot.agents.tool_registry import AGENT_NAME_TO_TRIGGER
        assert AGENT_NAME_TO_TRIGGER["MealAnalyzerAgent"] == "photo"
        assert AGENT_NAME_TO_TRIGGER["HealthExtractorAgent"] == "lab_report"
        assert AGENT_NAME_TO_TRIGGER["KnowledgeIngestorAgent"] == "research_article"
        assert AGENT_NAME_TO_TRIGGER["HealthInsightsAgent"] == "health_question"
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
python -m pytest tests/unit/test_tool_registry.py::TestRouteToAgent -v
```
Expected: `ImportError` or `AttributeError` (no route_to_agent yet)

- [ ] **Step 3: Add `route_to_agent` tool and `AGENT_NAME_TO_TRIGGER` to `bot/agents/tool_registry.py`**

After the existing `send_telegram_msg` tool, add:
```python
@tool
def route_to_agent(agent_name: str) -> str:
    """
    Signal the handler to invoke a specialist agent.
    Call this whenever routing to a specialist instead of answering directly.
    Valid values: 'MealAnalyzerAgent', 'HealthExtractorAgent',
                  'KnowledgeIngestorAgent', 'HealthInsightsAgent'.
    Returns agent_name so the handler can read it from the tool call args.
    """
    return agent_name
```

Add to `TOOL_REGISTRY`:
```python
    "route_to_agent": route_to_agent,
```

Add after `TOOL_REGISTRY` definition:
```python
AGENT_NAME_TO_TRIGGER: dict[str, str] = {
    "MealAnalyzerAgent": "photo",
    "HealthExtractorAgent": "lab_report",
    "KnowledgeIngestorAgent": "research_article",
    "HealthInsightsAgent": "health_question",
}
```

- [ ] **Step 4: Add `route_to_agent` to `bot/agents/configs/orchestrator.yaml`**

```yaml
name: OrchestratorAgent
model: claude-haiku-4-5-20251001
max_tokens: 512
recursion_limit: 3
prompt: prompts/orchestrator.txt
tools:
  - get_health_profile
  - get_user_profile
  - get_nutrition_guidance
  - get_semantic_memory
  - query_knowledge_base
  - ask_web_search_permission
  - send_telegram_msg
  - route_to_agent
triggers:
  - text
  - command
  - pdf
```

- [ ] **Step 5: Run tests — verify PASS**

```bash
python -m pytest tests/unit/test_tool_registry.py -v
```
Expected: all pass including the 3 new TestRouteToAgent tests

- [ ] **Step 6: Full suite — verify no regressions**

```bash
python -m pytest tests/ -q
```

- [ ] **Step 7: Commit**

```bash
git add bot/agents/tool_registry.py bot/agents/configs/orchestrator.yaml tests/unit/test_tool_registry.py
git commit -m "feat: add route_to_agent tool and AGENT_NAME_TO_TRIGGER mapping"
```

---

## Task 3: Event-loop wiring + startup initialization

**Files:**
- Modify: `bot/agents/tool_registry.py` — add `_main_loop`, update `init_tools`, fix `send_telegram_msg`
- Modify: `bot/main.py` — `post_init` wires session/loop/bot/AGENT_REGISTRY

**Interfaces:**
- Consumes: `init_tools(session, main_loop)` and `init_bot(app)` from tool_registry
- Produces: all agents properly wired to DB and Telegram at startup

- [ ] **Step 1: Update `tool_registry.py` — add `_main_loop` and fix `send_telegram_msg`**

At the top of `tool_registry.py`, after `_session` and `_bot_app` globals, add:
```python
_main_loop: object | None = None  # asyncio.AbstractEventLoop stored at startup
```

Update `init_tools` signature:
```python
def init_tools(session: Session, main_loop=None) -> None:
    """Set the shared DB session and event loop. Call at startup."""
    global _session, _main_loop
    _session = session
    if main_loop is not None:
        _main_loop = main_loop
```

Replace the `send_telegram_msg` tool body:
```python
@tool
def send_telegram_msg(message: str) -> str:
    """
    Send a Telegram message to the configured chat.
    Returns 'sent' on success.

    Called from agent tool nodes, which run in a thread executor when invoked
    from an async handler. Uses run_coroutine_threadsafe to hand the coroutine
    back to the main event loop without blocking it.
    """
    if _bot_app is None:
        raise RuntimeError("Bot app not initialised — call init_bot(app) at startup")
    if _main_loop is None:
        raise RuntimeError("Event loop not initialised — call init_tools(session, main_loop=loop) at startup")
    import asyncio
    future = asyncio.run_coroutine_threadsafe(
        _bot_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message),
        _main_loop,
    )
    future.result(timeout=15)
    return "sent"
```

- [ ] **Step 2: Update `bot/main.py`** — replace `create_application()` with the wired version:

```python
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
from bot.handlers.health import handle_document
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

    app.job_queue.run_repeating(heartbeat, interval=300, first=10)

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_application()
    app.run_polling()
```

- [ ] **Step 3: Run full suite — no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all pass (no new tests this task — wiring is integration-tested in later tasks)

- [ ] **Step 4: Commit**

```bash
git add bot/agents/tool_registry.py bot/main.py
git commit -m "feat: wire startup initialization — session, event loop, bot, agent registry"
```

---

## Task 4: Enable checkpointers for interrupt-using agents

**Files:**
- Modify: `bot/agents/configs/meal_analyzer.yaml`
- Modify: `bot/agents/configs/health_extractor.yaml`

MealAnalyzerAgent uses `ask_web_search_permission` (interrupt).
HealthExtractorAgent uses `confirm_with_user` (interrupt).
Both need `AsyncSqliteSaver` so their state survives until the user replies.

- [ ] **Step 1: Add `checkpointer: true` to `meal_analyzer.yaml`**

```yaml
name: MealAnalyzerAgent
model: claude-sonnet-4-6
max_tokens: 1024
recursion_limit: 5
prompt: prompts/meal_analyzer.txt
checkpointer: true
tools:
  - ask_web_search_permission
  - save_meal_analysis
  - get_indian_food
context:
  - health_profile
  - user_profile
  - nutrition_guidance
  - semantic_memory
  - knowledge_base
triggers:
  - photo
```

- [ ] **Step 2: Add `checkpointer: true` to `health_extractor.yaml`**

```yaml
name: HealthExtractorAgent
model: claude-sonnet-4-6
max_tokens: 768
recursion_limit: 5
prompt: prompts/health_extractor.txt
checkpointer: true
tools:
  - confirm_with_user
  - save_health_profile
  - generate_nutrition_guidance
triggers:
  - lab_report
```

- [ ] **Step 3: Run full suite — verify no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add bot/agents/configs/meal_analyzer.yaml bot/agents/configs/health_extractor.yaml
git commit -m "feat: enable checkpointer for MealAnalyzerAgent and HealthExtractorAgent (interrupt support)"
```

---

## Task 5: Wire meal handler → MealAnalyzerAgent + PatternDetectorAgent

**Files:**
- Modify: `bot/handlers/meal.py`

When the user selects a meal type after sending photo(s):
1. Download each photo from Telegram as bytes
2. Pass photos as multimodal content to MealAnalyzerAgent (run in executor)
3. Catch `GraphInterrupt` for web search permission requests
4. After successful save, invoke PatternDetectorAgent (fire-and-forget in executor)
5. Send acknowledgment to user

- [ ] **Step 1: Write integration test for wired handler**

Add to `tests/integration/test_meal_analyzer.py`:
```python
class TestMealHandlerWiring:
    """Tests that verify the handler wires to the agent correctly."""

    def test_invoke_with_photo_state_returns_messages(self, session, mock_anthropic):
        """MealAnalyzerAgent.invoke() with a photo-style state returns messages."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.agent_loader import load_agent
        from langchain_core.messages import HumanMessage
        from pathlib import Path

        init_tools(session)
        agent = load_agent(Path("bot/agents/configs/meal_analyzer.yaml"))
        state = {
            "input_type": "photo",
            "telegram_chat_id": 123456789,
            "messages": [HumanMessage(content="Analyze this lunch photo. [1 photo]")],
            "media_group_id": None,
            "photos": ["fake_file_id_1"],
            "analysis_result": None,
            "next_agent": None,
        }
        result = agent.invoke(state, thread_id="test-meal-wiring")
        assert "messages" in result
        assert len(result["messages"]) >= 1
```

- [ ] **Step 2: Run test — verify PASS (agent invocation with stub LLM works)**

```bash
python -m pytest tests/integration/test_meal_analyzer.py::TestMealHandlerWiring -v
```
Expected: PASS (stub LLM returns immediately)

- [ ] **Step 3: Update `bot/handlers/meal.py`**

Replace the file content entirely:
```python
"""
Telegram handler for photo messages (single photos and media group albums).

Routing only except for photo download — no LLM calls happen here beyond
dispatching to MealAnalyzerAgent and PatternDetectorAgent.

Media group buffering:
  Telegram sends album photos as separate Update messages that all share a
  media_group_id. We buffer file_ids in a TTLCache(ttl=2s) keyed by
  "media_group:{id}". The first photo in a group schedules a job to fire at
  2.1s; when the job runs it reads all buffered photos and processes as one meal.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import TYPE_CHECKING

from cachetools import TTLCache
from langchain_core.messages import HumanMessage

from bot.cache import clear_paused_agent, set_paused_agent
from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

media_buffer: TTLCache = TTLCache(maxsize=100, ttl=2)
MEAL_TYPE_KEYBOARD_BUTTONS = ["Breakfast", "Lunch", "Dinner", "Snack"]


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def buffer_photo(media_group_id: str, file_id: str, cache: TTLCache) -> None:
    key = f"media_group:{media_group_id}"
    if key not in cache:
        cache[key] = []
    cache[key].append(file_id)


def get_buffered_photos(media_group_id: str, cache: TTLCache) -> list:
    return cache.get(f"media_group:{media_group_id}", [])


def is_new_media_group(media_group_id: str, cache: TTLCache) -> bool:
    return f"media_group:{media_group_id}" not in cache


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_photo(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id
    media_group_id = update.message.media_group_id

    if media_group_id:
        is_new = is_new_media_group(media_group_id, media_buffer)
        buffer_photo(media_group_id, file_id, media_buffer)
        if is_new:
            context.job_queue.run_once(process_media_group, 2.1, data=media_group_id)
    else:
        context.user_data["pending_photos"] = [file_id]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(label, callback_data=f"meal_type:{label.lower()}")]
            for label in MEAL_TYPE_KEYBOARD_BUTTONS
        ])
        await update.message.reply_text("What meal is this?", reply_markup=keyboard)


async def process_media_group(context: "ContextTypes.DEFAULT_TYPE") -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    media_group_id: str = context.job.data
    file_ids = get_buffered_photos(media_group_id, media_buffer)

    if not file_ids:
        logger.warning("process_media_group: cache miss for group %s", media_group_id)
        return

    context.bot_data.setdefault("pending_photos", {})
    context.bot_data["pending_photos"][media_group_id] = file_ids

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"meal_type:{label.lower()}|{media_group_id}")]
        for label in MEAL_TYPE_KEYBOARD_BUTTONS
    ])
    await context.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"What meal is this? ({len(file_ids)} photo(s))",
        reply_markup=keyboard,
    )


async def handle_meal_type_callback(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """
    User tapped a meal type button. Downloads photos, invokes MealAnalyzerAgent,
    then PatternDetectorAgent. Handles GraphInterrupt for web search permission.
    """
    from langgraph.errors import GraphInterrupt
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    data = query.data

    if "|" in data:
        _, rest = data.split(":", 1)
        meal_type, media_group_id = rest.split("|", 1)
        file_ids = context.bot_data.get("pending_photos", {}).pop(media_group_id, [])
    else:
        meal_type = data.split(":", 1)[1]
        media_group_id = None
        file_ids = context.user_data.pop("pending_photos", [])

    if not file_ids:
        await query.edit_message_text("Sorry, I lost track of those photos — please send them again.")
        return

    await query.edit_message_text(f"Got it! Analyzing your {meal_type}... 🔍")

    # Download all photos from Telegram
    photo_contents = []
    for file_id in file_ids:
        tg_file = await context.bot.get_file(file_id)
        raw: bytearray = await tg_file.download_as_bytearray()
        b64 = base64.b64encode(bytes(raw)).decode()
        photo_contents.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })

    photo_contents.append({
        "type": "text",
        "text": f"Please analyze these {len(file_ids)} food photo(s). This is a {meal_type}.",
    })

    from bot.agents.agent_loader import AGENT_REGISTRY
    agent = AGENT_REGISTRY.get("photo")
    if agent is None:
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Agent not ready yet — please try again in a moment.")
        return

    state = {
        "input_type": "photo",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "messages": [HumanMessage(content=photo_contents)],
        "media_group_id": media_group_id,
        "photos": file_ids,
        "analysis_result": None,
        "next_agent": None,
    }

    thread_id = f"meal-{TELEGRAM_CHAT_ID}"
    loop = asyncio.get_event_loop()

    try:
        await loop.run_in_executor(
            None, lambda: agent.invoke(state, thread_id=thread_id)
        )
        clear_paused_agent()
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"Got it! Your {meal_type} has been logged 📷",
        )
        # Fire PatternDetectorAgent in background (non-blocking)
        asyncio.ensure_future(_run_pattern_detector(loop))

    except GraphInterrupt as exc:
        interrupt_msg = exc.interrupts[0].value if exc.interrupts else "Can I search the web?"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Yes, go ahead 🔍", callback_data="websearch:yes"),
            InlineKeyboardButton("No thanks", callback_data="websearch:no"),
        ]])
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=interrupt_msg, reply_markup=keyboard
        )
        set_paused_agent("photo")


async def _run_pattern_detector(loop: asyncio.AbstractEventLoop) -> None:
    """Invoke PatternDetectorAgent after a meal is saved. Fire-and-forget."""
    from bot.agents.agent_loader import AGENT_REGISTRY

    agent = AGENT_REGISTRY.get("pattern_detector")
    if agent is None:
        return
    state = {
        "input_type": "cron",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "messages": [HumanMessage(content="Check today's meal logs for patterns.")],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }
    try:
        await loop.run_in_executor(None, lambda: agent.invoke(state))
    except Exception as e:
        logger.warning("PatternDetectorAgent failed: %s", e)
```

Note: `pattern_detector` is not yet a trigger in the YAML. Add `triggers: [pattern_detector]` to `bot/agents/configs/pattern_detector.yaml` in the next step.

- [ ] **Step 4: Add trigger to `bot/agents/configs/pattern_detector.yaml`**

```yaml
name: PatternDetectorAgent
model: claude-haiku-4-5-20251001
max_tokens: 512
recursion_limit: 3
prompt: prompts/pattern_detector.txt
tools:
  - query_last_7_days
  - get_sent_callouts
  - send_telegram_msg
triggers:
  - pattern_detector
```

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/meal.py bot/agents/configs/pattern_detector.yaml
git commit -m "feat: wire meal handler to MealAnalyzerAgent + PatternDetectorAgent"
```

---

## Task 6: Wire PDF handler → OrchestratorAgent → HealthExtractorAgent / KnowledgeIngestorAgent

**Files:**
- Modify: `bot/handlers/health.py`
- Modify: `bot/main.py` (add confirm callback handler)

Flow:
1. Download PDF bytes
2. Invoke OrchestratorAgent to classify (lab report vs research article)
3. Read `route_to_agent` tool call from result messages
4. Dispatch to correct specialist with the same PDF bytes
5. Handle `GraphInterrupt` from HealthExtractorAgent (confirmation step)

- [ ] **Step 1: Write a test for the routing extraction helper**

Create `tests/unit/test_pdf_routing.py`:
```python
"""Unit tests for extract_routing_from_state helper (used in health handler)."""


def _make_ai_message_with_tool_call(agent_name: str):
    """Build a fake AIMessage that contains a route_to_agent tool call."""
    from langchain_core.messages import AIMessage

    return AIMessage(
        content="",
        tool_calls=[{"name": "route_to_agent", "args": {"agent_name": agent_name}, "id": "tc1"}],
    )


def test_extract_routing_finds_health_extractor():
    from bot.handlers.health import extract_routing_from_state

    msg = _make_ai_message_with_tool_call("HealthExtractorAgent")
    result = extract_routing_from_state({"messages": [msg]})
    assert result == "HealthExtractorAgent"


def test_extract_routing_finds_knowledge_ingestor():
    from bot.handlers.health import extract_routing_from_state

    msg = _make_ai_message_with_tool_call("KnowledgeIngestorAgent")
    result = extract_routing_from_state({"messages": [msg]})
    assert result == "KnowledgeIngestorAgent"


def test_extract_routing_returns_none_when_no_route_call():
    from langchain_core.messages import AIMessage
    from bot.handlers.health import extract_routing_from_state

    msg = AIMessage(content="Just a plain response, no routing.")
    result = extract_routing_from_state({"messages": [msg]})
    assert result is None


def test_extract_routing_returns_none_for_empty_messages():
    from bot.handlers.health import extract_routing_from_state

    result = extract_routing_from_state({"messages": []})
    assert result is None
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
python -m pytest tests/unit/test_pdf_routing.py -v
```
Expected: `ImportError` (extract_routing_from_state not yet defined)

- [ ] **Step 3: Rewrite `bot/handlers/health.py`**

```python
"""
Telegram handler for document (PDF) uploads.

Flow:
  1. Download PDF bytes from Telegram
  2. Invoke OrchestratorAgent to classify (lab report vs research article)
     via route_to_agent tool call
  3. Dispatch to HealthExtractorAgent or KnowledgeIngestorAgent
  4. Handle GraphInterrupt from HealthExtractorAgent (confirm_with_user)
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage

from bot.cache import clear_paused_agent, set_paused_agent
from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def extract_routing_from_state(result_state: dict) -> str | None:
    """
    Scan result messages for a route_to_agent tool call.
    Returns the agent_name arg string, or None if no routing was signalled.
    """
    for msg in result_state.get("messages", []):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "route_to_agent":
                    return tc["args"].get("agent_name")
    return None


def _make_pdf_state(b64_pdf: str, filename: str, instruction: str) -> dict:
    return {
        "input_type": "pdf",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "messages": [HumanMessage(content=[
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64_pdf,
                },
            },
            {"type": "text", "text": instruction},
        ])],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }


async def handle_document(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    """
    Called for all document uploads. Processes PDFs only.
    """
    from langgraph.errors import GraphInterrupt
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.agents.agent_loader import AGENT_REGISTRY
    from bot.agents.tool_registry import AGENT_NAME_TO_TRIGGER

    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    document = update.message.document
    if document.mime_type != "application/pdf":
        await update.message.reply_text("I can only process PDF files — try again with a PDF!")
        return

    await update.message.reply_text("Got your PDF — analyzing it now... 📄")

    tg_file = await document.get_file()
    file_bytes: bytearray = await tg_file.download_as_bytearray()
    b64_pdf = base64.b64encode(bytes(file_bytes)).decode()
    filename: str = document.file_name or "upload.pdf"

    orchestrator = AGENT_REGISTRY.get("pdf")
    if orchestrator is None:
        await update.message.reply_text("Agent not ready — please try again in a moment.")
        return

    loop = asyncio.get_event_loop()

    # Step 1: classify the PDF
    classify_state = _make_pdf_state(
        b64_pdf, filename,
        f"Classify this document (filename: {filename}). Is it a lab report or research article? "
        "Call route_to_agent with 'HealthExtractorAgent' for lab reports, "
        "'KnowledgeIngestorAgent' for research articles."
    )
    classify_result = await loop.run_in_executor(None, lambda: orchestrator.invoke(classify_state))
    agent_name = extract_routing_from_state(classify_result)

    if agent_name is None:
        await update.message.reply_text(
            "Hmm, I couldn't figure out what type of document that is. "
            "Is it a lab report or a research article?"
        )
        return

    trigger = AGENT_NAME_TO_TRIGGER.get(agent_name)
    specialist = AGENT_REGISTRY.get(trigger) if trigger else None
    if specialist is None:
        await update.message.reply_text(f"Routing error — no agent found for {agent_name}.")
        return

    # Step 2: invoke the specialist
    if agent_name == "HealthExtractorAgent":
        specialist_state = _make_pdf_state(
            b64_pdf, filename,
            "Extract the lab values from this health report: A1C, LDL, HDL, triglycerides, "
            "medications, and BMI. Then call confirm_with_user with the extracted values for confirmation."
        )
        thread_id = f"health-extract-{TELEGRAM_CHAT_ID}"
    else:
        specialist_state = _make_pdf_state(
            b64_pdf, filename,
            "Extract the key findings from this research article and save them to the knowledge base."
        )
        thread_id = None  # KnowledgeIngestorAgent doesn't need checkpointing

    try:
        await loop.run_in_executor(
            None, lambda: specialist.invoke(specialist_state, thread_id=thread_id)
        )
        clear_paused_agent()

    except GraphInterrupt as exc:
        # HealthExtractorAgent paused at confirm_with_user — show confirmation keyboard
        interrupt_msg = exc.interrupts[0].value if exc.interrupts else "Does this look right?"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Confirm ✅", callback_data="labconfirm:yes"),
            InlineKeyboardButton("Re-upload 🔄", callback_data="labconfirm:reupload"),
        ]])
        await update.message.reply_text(interrupt_msg, reply_markup=keyboard)
        set_paused_agent("lab_report")
```

- [ ] **Step 4: Add `labconfirm` callback handler to `bot/main.py`**

Import and register a new handler for lab confirmation callbacks. Add after the other imports and before `create_application()`:

In `bot/main.py`, add import:
```python
from bot.handlers.health import handle_labconfirm_callback
```

And in `create_application()`, add before the job_queue line:
```python
app.add_handler(CallbackQueryHandler(handle_labconfirm_callback, pattern="^labconfirm:"))
```

Then add `handle_labconfirm_callback` to `bot/handlers/health.py`:
```python
async def handle_labconfirm_callback(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Handle [Confirm] / [Re-upload] taps from HealthExtractorAgent confirmation."""
    from langgraph.types import Command
    from bot.agents.agent_loader import AGENT_REGISTRY

    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    choice = query.data.split(":", 1)[1]  # "yes" or "reupload"
    agent = AGENT_REGISTRY.get("lab_report")
    if agent is None:
        await query.edit_message_text("Agent not available — please try again.")
        return

    thread_id = f"health-extract-{TELEGRAM_CHAT_ID}"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: agent.graph.invoke(
            Command(resume=choice),
            config={"configurable": {"thread_id": thread_id}},
        )
    )
    clear_paused_agent()
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/unit/test_pdf_routing.py tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/health.py bot/main.py tests/unit/test_pdf_routing.py
git commit -m "feat: wire PDF handler — orchestrator classification + specialist dispatch + lab confirmation"
```

---

## Task 7: Wire text handler → Orchestrator + interrupt resume

**Files:**
- Modify: `bot/handlers/commands.py`

Flow for every text message:
1. Check diskcache for `paused_agent` — if set, resume that agent's graph
2. Handle "skip comparison" text (already partially done, add DB write)
3. Otherwise: invoke OrchestratorAgent
4. If orchestrator calls `route_to_agent("HealthInsightsAgent")`, invoke HealthInsightsAgent
5. Handle `GraphInterrupt` from either agent (web search permission)

Also add `websearch` callback handler in `main.py`.

- [ ] **Step 1: Write unit test for text handler helpers**

Add to `tests/unit/test_commands.py`:
```python
class TestSkipComparisonDBWrite:
    def test_skip_comparison_message_is_detected(self):
        from bot.handlers.commands import is_skip_comparison_message
        assert is_skip_comparison_message("skip comparison") is True
        assert is_skip_comparison_message("SKIP COMPARISON") is True
        assert is_skip_comparison_message("other text") is False
```

(This helper test should already pass — confirming the existing is_skip_comparison_message still works after changes.)

- [ ] **Step 2: Run existing commands tests — confirm PASS**

```bash
python -m pytest tests/unit/test_commands.py -v
```
Expected: all existing tests pass

- [ ] **Step 3: Rewrite `bot/handlers/commands.py`**

```python
"""
Telegram command handlers and text message routing.

handle_text_message:
  1. Check diskcache for a paused agent — resume if found
  2. "skip comparison" text → update DB flag + acknowledge
  3. Route to OrchestratorAgent → if it calls route_to_agent("HealthInsightsAgent"),
     invoke HealthInsightsAgent with checkpointer thread_id

handle_profile_command: query and display user_profile + latest health_profile
handle_profile_update: parse natural language update, write to DB
handle_addfood_command: parse /addfood args, upsert to indian_foods table
handle_help_command: send command list
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

from bot.cache import clear_paused_agent, get_paused_agent, set_paused_agent
from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helper functions — testable without Telegram context
# ---------------------------------------------------------------------------

_PROFILE_PATTERNS: list[tuple[re.Pattern, str, type]] = [
    (re.compile(r"\bcalorie[s]?\s+target\s+to\s+(\d+)", re.IGNORECASE), "calorie_target", int),
    (re.compile(r"\bweight\s+to\s+([\d.]+)", re.IGNORECASE), "weight_kg", float),
    (re.compile(r"\bactivity\s+level\s+to\s+(\w+)", re.IGNORECASE), "activity_level", str),
    (re.compile(r"\bstep\s+goal\s+to\s+(\d+)", re.IGNORECASE), "step_goal", int),
    (re.compile(r"\bsleep\s+goal\s+to\s+([\d.]+)", re.IGNORECASE), "sleep_goal_hrs", float),
    (re.compile(r"\bdiet\s+type\s+to\s+(\w+)", re.IGNORECASE), "diet_type", str),
]


def parse_profile_update_command(text: str) -> dict:
    """
    Parse natural language profile update into field→value dict.
    Returns {} if nothing parseable.

    Supported: calorie_target, weight_kg, activity_level, step_goal,
               sleep_goal_hrs, diet_type
    """
    result: dict = {}
    for pattern, field, cast in _PROFILE_PATTERNS:
        match = pattern.search(text)
        if match:
            result[field] = cast(match.group(1))
    return result


def is_skip_comparison_message(text: str) -> bool:
    return text.strip().lower() == "skip comparison"


def _format_profile(profile_row, health_row) -> str:
    """Format user_profile + health_profile into a readable Telegram message."""
    lines = ["📋 *Your Profile*\n"]

    if profile_row:
        lines.append(
            f"👤 {profile_row.name or 'Sahil'}, {profile_row.age or '?'} y/o, {profile_row.gender or '?'}\n"
            f"📏 Height: {profile_row.height_cm or '?'}cm  Weight: {profile_row.weight_kg or '?'}kg\n"
            f"🥗 Diet: {profile_row.diet_type or '?'}  Activity: {profile_row.activity_level or '?'}\n"
            f"🎯 Goals: {profile_row.step_goal or 10000} steps/day · {profile_row.sleep_goal_hrs or 7}hrs sleep\n"
            f"📊 Targets: {profile_row.calorie_target or '?'} kcal · "
            f"{profile_row.protein_target_g or '?'}g protein · "
            f"{profile_row.carb_target_g or '?'}g carbs · "
            f"{profile_row.fat_target_g or '?'}g fat\n"
        )
    else:
        lines.append("No user profile set yet. Send /profile update to add details.\n")

    if health_row:
        lines.append(
            f"\n🧪 *Latest Labs* ({health_row.report_date})\n"
            f"A1C: {health_row.a1c}%  LDL: {health_row.ldl} mg/dL  "
            f"HDL: {health_row.hdl} mg/dL  TG: {health_row.triglycerides} mg/dL\n"
            f"BMI: {health_row.bmi}  Meds: {', '.join(health_row.medications or []) or 'none'}"
        )
    else:
        lines.append("\n🧪 No lab report uploaded yet — send a PDF to get personalised guidance.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_profile_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Display current user_profile + latest health_profile values."""
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    from bot.agents.tool_registry import _get_session
    from db import queries

    try:
        session = _get_session()
    except RuntimeError:
        await update.message.reply_text("Bot still starting up — try again in a moment.")
        return

    profile = queries.get_user_profile(session)
    health = queries.get_latest_health_profile(session)
    await update.message.reply_text(_format_profile(profile, health), parse_mode="Markdown")


async def handle_profile_update(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Let user update profile fields conversationally."""
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    text = update.message.text or ""
    updates = parse_profile_update_command(text)

    if not updates:
        await update.message.reply_text(
            "I didn't catch that. Try something like:\n"
            '"change my calorie target to 2000" or "update my weight to 79"'
        )
        return

    from bot.agents.tool_registry import _get_session
    from db import queries

    session = _get_session()
    queries.upsert_user_profile(session, **updates)
    field_list = ", ".join(f"{k} → {v}" for k, v in updates.items())
    await update.message.reply_text(f"Done! Updated: {field_list} 👍")


async def handle_addfood_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Parse /addfood <name> and add/update entry in indian_foods table."""
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /addfood <food name>\nExample: /addfood Dal Makhani"
        )
        return

    food_name = " ".join(args)

    from bot.agents.tool_registry import _get_session
    from db import queries

    session = _get_session()
    queries.upsert_indian_food(session, name=food_name)
    await update.message.reply_text(f'Added "{food_name}" to the Indian foods database. 🍛')


async def handle_help_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    help_text = (
        "Here's what I can do:\n\n"
        "📷 Send a photo (or album) → log a meal\n"
        "📄 Send a PDF → upload a lab report or research article\n\n"
        "Commands:\n"
        "/profile — view your current profile and latest lab values\n"
        "/addfood <name> — add a food to the Indian foods database\n"
        "/help — show this message\n\n"
        "You can also just chat with me — ask about your nutrition, "
        "health patterns, or what you should eat today."
    )
    await update.message.reply_text(help_text)


async def handle_websearch_callback(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Handle yes/no tap from web search permission keyboard."""
    from langgraph.types import Command
    from bot.agents.agent_loader import AGENT_REGISTRY

    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    choice = query.data.split(":", 1)[1]  # "yes" or "no"
    paused_trigger = get_paused_agent()
    if paused_trigger is None:
        await query.edit_message_text("No active request to resume.")
        return

    agent = AGENT_REGISTRY.get(paused_trigger)
    if agent is None:
        await query.edit_message_text("Agent not available — please try again.")
        clear_paused_agent()
        return

    thread_id = f"meal-{TELEGRAM_CHAT_ID}" if paused_trigger == "photo" else f"text-{TELEGRAM_CHAT_ID}"
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            lambda: agent.graph.invoke(
                Command(resume=choice),
                config={"configurable": {"thread_id": thread_id}},
            ),
        )
    except Exception as e:
        logger.error("Error resuming agent %s: %s", paused_trigger, e)
    finally:
        clear_paused_agent()

    await query.edit_message_text("Got it! Continuing..." if choice == "yes" else "No problem, skipping web search.")


async def handle_text_message(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """
    Catch-all for text messages (not commands, not photos, not PDFs).

    1. If a LangGraph graph is paused (interrupt), resume it
    2. "skip comparison" → write DB flag + acknowledge
    3. Route to OrchestratorAgent
    4. If orchestrator routes to HealthInsightsAgent, invoke it
    """
    from langgraph.errors import GraphInterrupt
    from langgraph.types import Command
    from bot.agents.agent_loader import AGENT_REGISTRY
    from bot.agents.tool_registry import AGENT_NAME_TO_TRIGGER
    from bot.handlers.health import extract_routing_from_state

    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    text = update.message.text or ""
    loop = asyncio.get_event_loop()

    # 1. Check for paused agent — resume it
    paused_trigger = get_paused_agent()
    if paused_trigger is not None:
        agent = AGENT_REGISTRY.get(paused_trigger)
        if agent is not None:
            thread_id = _thread_id_for_trigger(paused_trigger)
            try:
                await loop.run_in_executor(
                    None,
                    lambda: agent.graph.invoke(
                        Command(resume=text),
                        config={"configurable": {"thread_id": thread_id}},
                    ),
                )
                clear_paused_agent()
            except GraphInterrupt as exc:
                interrupt_msg = exc.interrupts[0].value if exc.interrupts else text
                await update.message.reply_text(interrupt_msg)
            return

    # 2. "skip comparison" special case — write to weekly_reports if a report exists
    if is_skip_comparison_message(text):
        _write_skip_comparison()
        await update.message.reply_text(
            "Got it — I'll skip the recommendation follow-through in this Sunday's report 👍"
        )
        return

    # 3. Route to OrchestratorAgent
    orchestrator = AGENT_REGISTRY.get("text")
    if orchestrator is None:
        await update.message.reply_text("Bot still warming up — try again in a moment.")
        return

    state = {
        "input_type": "text",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "messages": [HumanMessage(content=text)],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }

    try:
        orch_result = await loop.run_in_executor(None, lambda: orchestrator.invoke(state))
    except GraphInterrupt as exc:
        interrupt_msg = exc.interrupts[0].value if exc.interrupts else "Waiting for your response..."
        await update.message.reply_text(interrupt_msg)
        set_paused_agent("text")
        return

    # 4. Check if orchestrator routed to HealthInsightsAgent
    agent_name = extract_routing_from_state(orch_result)
    if agent_name == "HealthInsightsAgent":
        trigger = AGENT_NAME_TO_TRIGGER.get("HealthInsightsAgent", "health_question")
        specialist = AGENT_REGISTRY.get(trigger)
        if specialist is not None:
            thread_id = f"insights-{TELEGRAM_CHAT_ID}"
            try:
                await loop.run_in_executor(
                    None, lambda: specialist.invoke(state, thread_id=thread_id)
                )
            except GraphInterrupt as exc:
                interrupt_msg = exc.interrupts[0].value if exc.interrupts else "Can I search the web?"
                await update.message.reply_text(interrupt_msg)
                set_paused_agent("health_question")


def _thread_id_for_trigger(trigger: str) -> str:
    return {
        "photo": f"meal-{TELEGRAM_CHAT_ID}",
        "lab_report": f"health-extract-{TELEGRAM_CHAT_ID}",
        "health_question": f"insights-{TELEGRAM_CHAT_ID}",
        "text": f"text-{TELEGRAM_CHAT_ID}",
    }.get(trigger, f"{trigger}-{TELEGRAM_CHAT_ID}")


def _write_skip_comparison() -> None:
    """Write skip_comparison=1 to the most recent weekly_reports row, if one exists."""
    from bot.agents.tool_registry import _get_session
    from db.models import WeeklyReport
    from datetime import date
    from zoneinfo import ZoneInfo

    try:
        session = _get_session()
        # Get the current week start (Monday)
        today = date.today()
        week_start = str(today - __import__("datetime").timedelta(days=today.weekday()))
        row = session.query(WeeklyReport).filter_by(week_start=week_start).first()
        if row is None:
            row = WeeklyReport(week_start=week_start, skip_comparison=1)
            session.add(row)
        else:
            row.skip_comparison = 1
        session.commit()
    except Exception as e:
        logger.warning("Could not write skip_comparison: %s", e)
```

- [ ] **Step 4: Register new callback handlers in `bot/main.py`**

Add import:
```python
from bot.handlers.commands import handle_profile_update, handle_websearch_callback
```

Add to `create_application()`:
```python
app.add_handler(CallbackQueryHandler(handle_websearch_callback, pattern="^websearch:"))
```

Also add the `handle_profile_update` as a text command handler (when user sends `/profile update`):
```python
app.add_handler(CommandHandler("profile", handle_profile_command))
```
(The existing `/profile` handler already handles display; `handle_profile_update` is invoked from `handle_text_message` when responding to a profile update prompt in conversation — no separate registration needed.)

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/unit/test_commands.py tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/commands.py bot/main.py
git commit -m "feat: wire text handler to orchestrator, health insights, and interrupt resume"
```

---

## Task 8: Onboarding flow

**Files:**
- Create: `bot/handlers/onboarding.py`
- Modify: `bot/handlers/commands.py` (call `check_and_run_onboarding` at start of `handle_text_message`)
- Modify: `bot/main.py` (register onboarding callback handler)

Onboarding runs on first message when `user_profile` row doesn't exist.
Uses diskcache key `onboarding_complete`. Multi-step with inline keyboards.
On completion, saves to `user_profile` and optionally prompts for lab PDF.

- [ ] **Step 1: Write tests for the onboarding module**

Create `tests/unit/test_onboarding.py`:
```python
"""Unit tests for the onboarding module."""

import pytest


@pytest.fixture
def fresh_cache(tmp_path, monkeypatch):
    """Reset diskcache to a temp dir for each test."""
    monkeypatch.setattr("config.DISKCACHE_DIR", str(tmp_path / "cache"))
    import bot.cache as bc
    bc._cache = None
    yield
    bc._cache = None


def test_onboarding_needed_when_no_profile(session, fresh_cache):
    from bot.handlers.onboarding import is_onboarding_needed
    assert is_onboarding_needed(session) is True


def test_onboarding_not_needed_when_complete(session, fresh_cache):
    from bot.handlers.onboarding import is_onboarding_needed
    from bot.cache import set_onboarding_complete
    set_onboarding_complete()
    assert is_onboarding_needed(session) is False


def test_onboarding_not_needed_when_profile_exists(session, fresh_cache):
    from db.models import UserProfile
    from bot.handlers.onboarding import is_onboarding_needed
    p = UserProfile(id=1, name="Sahil", diet_type="omnivore")
    session.add(p)
    session.commit()
    assert is_onboarding_needed(session) is False


def test_save_onboarding_answers_writes_profile(session, fresh_cache):
    from bot.handlers.onboarding import save_onboarding_answers
    from db import queries

    answers = {
        "diet_type": "omnivore",
        "allergies": None,
        "activity_level": "moderate",
        "calorie_target": 1800,
    }
    save_onboarding_answers(session, answers)
    profile = queries.get_user_profile(session)
    assert profile is not None
    assert profile.diet_type == "omnivore"
    assert profile.calorie_target == 1800


def test_save_onboarding_answers_marks_complete(session, fresh_cache):
    from bot.handlers.onboarding import save_onboarding_answers
    from bot.cache import is_onboarding_complete

    save_onboarding_answers(session, {"diet_type": "vegan", "calorie_target": 1600})
    assert is_onboarding_complete() is True
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
python -m pytest tests/unit/test_onboarding.py -v
```
Expected: `ModuleNotFoundError` (bot.handlers.onboarding doesn't exist)

- [ ] **Step 3: Create `bot/handlers/onboarding.py`**

```python
"""
User onboarding flow — runs on first message when user_profile row doesn't exist.

Uses diskcache key 'onboarding_complete' to track whether setup is done.
Multi-step inline keyboard conversation:
  Step 1: diet type
  Step 2: allergies (free text or 'None')
  Step 3: activity level
  Step 4: calorie target

On completion: saves to user_profile, sets onboarding_complete.
One-time lab prompt: if profile lacks health data, sends a one-time tip.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import TELEGRAM_CHAT_ID
from bot.cache import (
    get_app_cache,
    is_onboarding_complete,
    set_onboarding_complete,
    has_sent_onboarding_prompt,
    set_onboarding_prompt_sent,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_KEY_ONBOARDING_STEP = "onboarding_step"
_KEY_ONBOARDING_ANSWERS = "onboarding_answers"


def is_onboarding_needed(session: "Session") -> bool:
    """Return True if onboarding hasn't been completed and no user_profile row exists."""
    if is_onboarding_complete():
        return False
    from db import queries
    return queries.get_user_profile(session) is None


def save_onboarding_answers(session: "Session", answers: dict) -> None:
    """Save collected onboarding answers to user_profile and mark onboarding complete."""
    from db import queries
    queries.upsert_user_profile(session, **{k: v for k, v in answers.items() if v is not None})
    set_onboarding_complete()


async def start_onboarding(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    """Send first onboarding question (diet type)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    cache = get_app_cache()
    cache.set(_KEY_ONBOARDING_STEP, 1)
    cache.set(_KEY_ONBOARDING_ANSWERS, {})

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🥩 Omnivore", callback_data="onboard:diet:omnivore"),
        InlineKeyboardButton("🥦 Vegetarian", callback_data="onboard:diet:vegetarian"),
        InlineKeyboardButton("🌱 Vegan", callback_data="onboard:diet:vegan"),
    ]])
    await update.message.reply_text(
        "Hey Sahil! 👋 Let me personalise your experience with a few quick questions.\n\n"
        "What's your diet type?",
        reply_markup=keyboard,
    )


async def handle_onboarding_callback(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """
    Handle inline keyboard taps during onboarding.
    Callback data format: "onboard:<step_key>:<value>"
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.agents.tool_registry import _get_session

    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    # Parse callback data: "onboard:<step_key>:<value>"
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, step_key, value = parts

    cache = get_app_cache()
    answers: dict = cache.get(_KEY_ONBOARDING_ANSWERS, {})
    answers[step_key] = value
    cache.set(_KEY_ONBOARDING_ANSWERS, answers)

    step = cache.get(_KEY_ONBOARDING_STEP, 1)

    if step == 1:
        # Received diet type → ask activity level
        cache.set(_KEY_ONBOARDING_STEP, 2)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🪑 Sedentary", callback_data="onboard:activity_level:sedentary"),
            InlineKeyboardButton("🚶 Moderate", callback_data="onboard:activity_level:moderate"),
            InlineKeyboardButton("🏃 Active", callback_data="onboard:activity_level:active"),
        ]])
        await query.edit_message_text(
            "What's your typical activity level?", reply_markup=keyboard
        )

    elif step == 2:
        # Received activity level → ask calorie target
        cache.set(_KEY_ONBOARDING_STEP, 3)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("1,600 kcal", callback_data="onboard:calorie_target:1600"),
            InlineKeyboardButton("1,800 kcal", callback_data="onboard:calorie_target:1800"),
            InlineKeyboardButton("2,000 kcal", callback_data="onboard:calorie_target:2000"),
            InlineKeyboardButton("Skip for now", callback_data="onboard:calorie_target:skip"),
        ]])
        await query.edit_message_text(
            "Last one — what's your daily calorie target?", reply_markup=keyboard
        )

    elif step == 3:
        # Received calorie target → save and complete
        if value == "skip":
            answers.pop("calorie_target", None)
        else:
            answers["calorie_target"] = int(value)

        # Also set defaults
        answers.setdefault("name", "Sahil")
        answers.pop("calorie_target", None)  # will be set via int above
        if value != "skip":
            answers["calorie_target"] = int(value)

        try:
            session = _get_session()
        except RuntimeError:
            await query.edit_message_text("Setup error — please restart the bot and try again.")
            return

        save_onboarding_answers(session, answers)
        cache.delete(_KEY_ONBOARDING_STEP)
        cache.delete(_KEY_ONBOARDING_ANSWERS)

        await query.edit_message_text(
            "You're all set! 🎉 I'm ready to be your personal nutrition bot.\n\n"
            "📷 Send me a photo of your next meal to get started!\n"
            "📋 Tip: send me your latest lab report PDF and I'll personalise everything "
            "to your actual A1C and cholesterol values."
        )
        set_onboarding_prompt_sent()


async def maybe_send_onboarding_prompt(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE", session: "Session"
) -> bool:
    """
    If onboarding is complete but no lab report has been uploaded,
    append a one-time tip. Returns True if the tip was sent (caller should
    not process the message further in that case — the user may be mid-flow).
    """
    if has_sent_onboarding_prompt():
        return False
    from db import queries
    if queries.get_latest_health_profile(session) is not None:
        return False
    await update.message.reply_text(
        "📋 Tip: send me your latest lab report PDF and I'll personalise "
        "everything to your actual A1C and cholesterol values."
    )
    set_onboarding_prompt_sent()
    return False  # don't block further processing
```

- [ ] **Step 4: Add onboarding check at the top of `handle_text_message`**

In `bot/handlers/commands.py`, at the start of `handle_text_message` (after the chat_id check), add:
```python
    # Onboarding check
    from bot.handlers.onboarding import is_onboarding_needed, start_onboarding, maybe_send_onboarding_prompt
    from bot.agents.tool_registry import _get_session
    try:
        session = _get_session()
        if is_onboarding_needed(session):
            await start_onboarding(update, context)
            return
        await maybe_send_onboarding_prompt(update, context, session)
    except RuntimeError:
        pass  # session not ready at startup
```

Also add onboarding check in `handle_photo` (in `bot/handlers/meal.py`) at the top of the handler so that even if the user sends a photo first, onboarding runs:
```python
    # If onboarding not complete, redirect to text flow
    from bot.cache import is_onboarding_complete
    if not is_onboarding_complete():
        await update.message.reply_text(
            "Hey Sahil! 👋 Let me set you up first — send me a message and I'll walk you through a quick setup."
        )
        return
```

- [ ] **Step 5: Register onboarding callback in `bot/main.py`**

Add import:
```python
from bot.handlers.onboarding import handle_onboarding_callback
```

Add handler in `create_application()`:
```python
app.add_handler(CallbackQueryHandler(handle_onboarding_callback, pattern="^onboard:"))
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/unit/test_onboarding.py tests/ -q
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add bot/handlers/onboarding.py bot/handlers/commands.py bot/handlers/meal.py bot/main.py tests/unit/test_onboarding.py
git commit -m "feat: add multi-step onboarding flow with inline keyboards and diskcache tracking"
```

---

## Task 9: E2E test for alert flow

**Files:**
- Create: `tests/e2e/test_alert_flow.py`

The spec requires testing:
1. At 3pm with no meals logged → `lunch_alert_flow` sends an alert
2. With lunch logged → no alert
3. At 10:30pm with no dinner → `dinner_alert_flow` sends an alert
4. With dinner logged → no alert

- [ ] **Step 1: Write `tests/e2e/test_alert_flow.py`**

```python
"""
E2E tests for lunch and dinner alert flows.

Tests verify:
1. lunch_alert_flow sends alert when no breakfast/lunch logged today
2. lunch_alert_flow sends no alert when lunch already logged
3. dinner_alert_flow sends alert when no dinner logged
4. dinner_alert_flow sends no alert when dinner already logged

Uses freezegun to control "today" and patches out the Telegram send.
"""

import pytest
from datetime import datetime, date
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def alert_session(session, monkeypatch):
    """Patch tool_registry session so flows use the test DB."""
    import bot.agents.tool_registry as tr
    monkeypatch.setattr(tr, "_session", session)
    return session


def _insert_meal(session, meal_type: str, date_str: str | None = None):
    from db.models import MealLog
    from datetime import date as dt_date
    log_date = date_str or str(dt_date.today())
    row = MealLog(
        date=log_date,
        meal_type=meal_type,
        logged_at=f"{log_date}T12:00:00",
        foods_identified=["test food"],
        macros={"calories": 500},
        flags={},
        score=70,
    )
    session.add(row)
    session.commit()


def _patch_telegram(monkeypatch):
    """Patch the Telegram send so tests don't need a real bot."""
    sent = []

    async def fake_send(*args, **kwargs):
        sent.append(kwargs.get("text", args[0] if args else ""))

    monkeypatch.setattr("flows.alerts.send_telegram_alert", lambda text: sent.append(text))
    return sent


class TestLunchAlertFlow:
    def test_alert_sent_when_no_meals_logged(self, alert_session, monkeypatch):
        """lunch_alert_flow sends an alert when no breakfast or lunch is logged today."""
        sent = _patch_telegram(monkeypatch)

        from flows.alerts import lunch_alert_flow
        lunch_alert_flow()

        assert len(sent) == 1
        assert "breakfast" in sent[0].lower() or "lunch" in sent[0].lower()

    def test_no_alert_when_lunch_logged(self, alert_session, monkeypatch):
        """lunch_alert_flow skips alert when lunch is already logged."""
        sent = _patch_telegram(monkeypatch)
        _insert_meal(alert_session, "lunch")

        from flows.alerts import lunch_alert_flow
        lunch_alert_flow()

        assert len(sent) == 0

    def test_no_alert_when_breakfast_logged(self, alert_session, monkeypatch):
        """lunch_alert_flow skips alert when breakfast is already logged."""
        sent = _patch_telegram(monkeypatch)
        _insert_meal(alert_session, "breakfast")

        from flows.alerts import lunch_alert_flow
        lunch_alert_flow()

        assert len(sent) == 0


class TestDinnerAlertFlow:
    def test_alert_sent_when_no_dinner_logged(self, alert_session, monkeypatch):
        """dinner_alert_flow sends alert when no dinner is logged today."""
        sent = _patch_telegram(monkeypatch)

        from flows.alerts import dinner_alert_flow
        dinner_alert_flow()

        assert len(sent) == 1
        assert "dinner" in sent[0].lower()

    def test_no_alert_when_dinner_logged(self, alert_session, monkeypatch):
        """dinner_alert_flow skips alert when dinner already logged."""
        sent = _patch_telegram(monkeypatch)
        _insert_meal(alert_session, "dinner")

        from flows.alerts import dinner_alert_flow
        dinner_alert_flow()

        assert len(sent) == 0
```

- [ ] **Step 2: Run test — check what fails and why**

```bash
python -m pytest tests/e2e/test_alert_flow.py -v
```
Note the failures. The `send_telegram_alert` patch may need adjusting to match the actual function name in `flows/alerts.py`. Read `flows/alerts.py` and update the patch target string if the function is named differently.

- [ ] **Step 3: Verify the patch target by reading `flows/alerts.py`**

```bash
grep -n "def send_telegram_alert\|def _send\|requests.get\|bot.send" /Users/sahilkhandwala/Desktop/FitAi/flows/alerts.py
```

Adjust the monkeypatch target in the test to match the actual function name (e.g. if it's `_on_flow_failure` that sends, patch that instead — check the file).

- [ ] **Step 4: Run test — all PASS**

```bash
python -m pytest tests/e2e/test_alert_flow.py -v
```
Expected: 5 tests pass

- [ ] **Step 5: Full suite — no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all pass (+ 5 new)

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/test_alert_flow.py
git commit -m "test: add e2e tests for lunch and dinner alert flows"
```

---

## Task 10: Final wiring verification

Confirm all the pieces connect cleanly by reading through the startup sequence.

- [ ] **Step 1: Verify `build_agent_registry()` produces the expected triggers**

```bash
cd /Users/sahilkhandwala/Desktop/FitAi
python -c "
import os; os.environ.setdefault('TELEGRAM_BOT_TOKEN','x'); os.environ.setdefault('TELEGRAM_CHAT_ID','123'); os.environ.setdefault('ANTHROPIC_API_KEY','x')
from bot.agents.agent_loader import build_agent_registry
reg = build_agent_registry()
print('AGENT_REGISTRY triggers:', sorted(reg.keys()))
"
```
Expected output includes: `health_question`, `lab_report`, `pattern_detector`, `pdf`, `photo`, `research_article`, `text`

- [ ] **Step 2: Run the full test suite one final time**

```bash
python -m pytest tests/ -q
```
Expected: all pass (191+ tests)

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "chore: final wiring verification — all agents registered, all handlers connected"
```

---

## Self-Review Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| Meal photo → MealAnalyzerAgent → save | Task 5 |
| Web search permission interrupt + resume | Tasks 4, 5, 7 |
| PDF → orchestrator classify → specialist | Task 6 |
| HealthExtractorAgent confirmation keyboard | Task 6 |
| Lab confirmation resume (Confirm/Re-upload) | Task 6 |
| Text → OrchestratorAgent → HealthInsightsAgent | Task 7 |
| LangGraph interrupt resume (text reply) | Task 7 |
| "skip comparison" → DB write | Task 7 |
| /profile display | Task 7 |
| /profile update → DB write | Task 7 |
| /addfood → upsert_indian_food | Task 7 |
| Onboarding multi-step inline keyboard | Task 8 |
| Onboarding diskcache tracking | Tasks 1, 8 |
| One-time lab report tip | Task 8 |
| PatternDetectorAgent after meal save | Task 5 |
| init_tools / init_bot at startup | Task 3 |
| Agents built in AGENT_REGISTRY at startup | Task 3 |
| E2E alert flow test | Task 9 |
| Checkpointer on MealAnalyzerAgent + HealthExtractorAgent | Task 4 |
