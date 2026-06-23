# bot/agents/tool_registry.py

## Summary
All callable LangGraph tools for FitAi agents, plus context loaders for system-prompt injection. Tools are decorated with @tool from langchain_core.tools. Uses a module-level _session set by init_tools() and _bot_app set by init_bot(). Exposes TOOL_REGISTRY (str → tool) and CONTEXT_LOADERS (str → callable returning formatted string block).

## Functions
- init_tools(session) — sets module-level _session; must be called at startup before any tool
- init_bot(app) — sets module-level _bot_app for Telegram sending
- _get_session() → Session — raises RuntimeError if not initialised
- get_health_profile() → dict | None — @tool; fetches latest lab profile
- get_user_profile() → dict | None — @tool; fetches singleton user profile
- get_nutrition_guidance() → list[dict] — @tool; fetches active guidance rules
- get_semantic_memory() → list[dict] — @tool; fetches all semantic memory facts
- query_knowledge_base() → list[dict] — @tool; loads all JSON files from KNOWLEDGE_BASE_DIR
- save_meal_analysis(meal_type, foods_identified, estimated_macros, glycemic_load, cholesterol_flags, a1c_flags, score, telegram_chat_id) → str — @tool; inserts meal log, returns "saved"
- query_todays_meals() → list[dict] — @tool; today's meals
- query_last_7_days() → dict — @tool; 7-day meals + health combined
- query_week_meals() → list[dict] — @tool; last 7 days meals
- query_last_2_days_meals() → list[dict] — @tool; last 2 days meals
- query_last_2_days_steps() → list[dict] — @tool; last 2 days step data
- query_last_2_days_sleep() → list[dict] — @tool; last 2 days sleep data
- save_health_profile(report_date, a1c, ldl, hdl, triglycerides, medications, bmi) → str — @tool; returns "saved" or "duplicate_date"
- generate_nutrition_guidance(new_lab_values, deactivate_ids, deactivate_remarks, reactivate_ids, new_rules) → str — @tool; 3-step guidance update, returns "done"
- get_last_week_recommendations() → dict | None — @tool; most recent weekly recommendations
- get_sent_callouts(date) → list[str] — @tool; pattern_type strings sent on date
- save_to_knowledge_base(filename, source, ingested_at, relevance_tags, findings) → str — @tool; writes JSON to KNOWLEDGE_BASE_DIR, returns "saved"
- ask_web_search_permission(reason) → str — @tool; LangGraph interrupt() for web search permission
- confirm_with_user(message) → str — @tool; LangGraph interrupt() for user confirmation
- send_telegram_msg(message) → str — @tool; sends Telegram message via _bot_app; returns "sent"; NOTE: asyncio.get_event_loop().run_until_complete() raises if called from running loop
- get_indian_food(name) → dict | None — @tool; looks up Indian food by name
- _meal_row_to_dict(row) → dict — internal helper, MealLog ORM row → dict
- _health_row_to_dict(row) → dict — internal helper, DailyHealthLog ORM row → dict
- _load_health_profile_context() → str — context loader; formats === LATEST LAB RESULTS === block
- _load_user_profile_context() → str — context loader; formats === USER PROFILE === block
- _load_nutrition_guidance_context() → str — context loader; formats === PERSONALISED NUTRITION RULES === block
- _load_semantic_memory_context() → str — context loader; formats === SEMANTIC MEMORY === block
- _load_knowledge_base_context() → str — context loader; formats === KNOWLEDGE BASE === block

## Non-function code
- `_session` — module-level Session, None until init_tools() called
- `_bot_app` — module-level Telegram Application, None until init_bot() called
- `LA` — ZoneInfo("America/Los_Angeles")
- `TOOL_REGISTRY` — dict mapping 21 tool name strings to @tool objects
- `CONTEXT_LOADERS` — dict mapping 5 context key strings to loader functions

## Imports
- asyncio, json, datetime, pathlib.Path, zoneinfo.ZoneInfo
- langchain_core.tools.tool
- langgraph.types.interrupt
- sqlalchemy.exc.IntegrityError
- sqlalchemy.orm.Session
- config (KNOWLEDGE_BASE_DIR, TELEGRAM_CHAT_ID)
- db.queries (all query functions)

## Imported by
- bot/agents/agent_loader.py — imports TOOL_REGISTRY, CONTEXT_LOADERS
- tests/unit/test_tool_registry.py — imports individual tools, init_tools

## Tags
agents, tools, langgraph, registry, telegram, knowledge-base

## Node path
bot/agents/tool_registry.py
