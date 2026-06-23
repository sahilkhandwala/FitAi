# Project Index

## Summary
FitAi is a standalone Telegram bot acting as Sahil's personal dietary nutritionist. It logs meals via photo analysis, extracts health data from lab PDF reports, ingests research articles, and delivers daily/weekly health insights — all targeted at reducing A1C, lowering LDL, raising HDL, and maintaining fitness. Two processes share a local SQLite database: the real-time Telegram bot (python-telegram-bot v20+) and scheduled Prefect flows (6 cron jobs).

## Tech Stack
Python 3.11+, python-telegram-bot v20+, LangGraph v0.4+ + langchain-anthropic, Claude Haiku/Sonnet/Opus (multi-agent), SQLite WAL mode (SQLAlchemy 2.0+), cachetools TTLCache, diskcache, Prefect v3+, aiohttp, PyMuPDF, pyyaml, zoneinfo, monocle-apptrace, Uptime Kuma, Open-Meteo

## Files
| File | Tags | Summary | Status |
|------|------|---------|--------|
| config.py | config, env, constants, telegram, anthropic | Central configuration: reads all env vars, exposes typed constants for the entire project | active |
| db/__init__.py | database, sqlalchemy, sqlite, factory | DB factory: get_engine() with WAL mode + create_all, get_session_factory() | active |
| bot/main.py | telegram, entrypoint, bot, handlers, heartbeat | Entry point: builds Application, registers all handlers, runs Uptime Kuma heartbeat job | active |
| bot/handlers/meal.py | telegram, handler, media-group, photo, cachetools, routing | Photo handler with TTLCache media group buffering; pure helpers + async Telegram handlers | active |
| bot/handlers/health.py | telegram, handler, pdf, routing, health | PDF document handler; validates mime type, downloads bytes, stubs agent routing | active |
| bot/handlers/commands.py | telegram, handler, commands, parsing, routing, profile | Command handlers + text routing; pure parse_profile_update_command and is_skip_comparison_message | active |
| tests/unit/test_meal_handler.py | tests, unit, meal, handler | Unit tests for buffer_photo, get_buffered_photos, is_new_media_group pure helpers | active |
| tests/unit/test_commands.py | tests, unit, commands, parsing | Unit tests for parse_profile_update_command and is_skip_comparison_message | active |
| tests/unit/test_media_group_buffer.py | tests, unit, media-group, cachetools | Unit tests for TTLCache key format and multi-group isolation | active |
| tests/conftest.py | tests, fixtures, database, mocks | Shared pytest fixtures: in-memory SQLite DB, knowledge_base temp dir, mock anthropic/fitbit/weather | active |
| bot/agents/pattern_detector.py | agents, patterns, langgraph, haiku, streak | PatternDetectorAgent + pure logic functions (get_escalation_tier, should_send_callout) — streak and pattern detection from meal logs | active |
| bot/agents/base_agent.py | agents, langgraph, base, infrastructure, state | AgentState TypedDict + BaseAgent class with LangGraph StateGraph wiring for all agents | active |
| bot/agents/tool_registry.py | agents, tools, langgraph, registry, telegram, knowledge-base | All @tool-decorated callables + CONTEXT_LOADERS + TOOL_REGISTRY + init_tools/init_bot | active |
| bot/agents/agent_loader.py | agents, loader, registry, yaml, config, infrastructure | Reads YAML configs, builds AGENT_REGISTRY of trigger → BaseAgent mappings | active |
| bot/agents/configs/orchestrator.yaml | config, yaml, agents | OrchestratorAgent config: Haiku, 512 tokens, text/command/pdf triggers | active |
| bot/agents/configs/meal_analyzer.yaml | config, yaml, agents | MealAnalyzerAgent config: Sonnet, 1024 tokens, photo trigger, 5 context injections | active |
| bot/agents/configs/health_extractor.yaml | config, yaml, agents | HealthExtractorAgent config: Sonnet, 768 tokens, lab_report trigger | active |
| bot/agents/configs/knowledge_ingestor.yaml | config, yaml, agents | KnowledgeIngestorAgent config: Sonnet, 1536 tokens, research_article trigger | active |
| bot/agents/configs/pattern_detector.yaml | config, yaml, agents | PatternDetectorAgent config: Haiku, 512 tokens, pattern_check trigger | active |
| bot/agents/configs/daily_summary.yaml | config, yaml, agents | DailySummaryAgent config: Haiku, 1536 tokens, daily_summary trigger, 3 context injections | active |
| bot/agents/configs/weekly_report.yaml | config, yaml, agents | WeeklyReportAgent config: Opus, 3072 tokens, weekly_report trigger, 5 context injections | active |
| bot/agents/configs/health_insights.yaml | config, yaml, agents | HealthInsightsAgent config: Opus, 1536 tokens, health_question trigger, checkpointer=true, 5 context injections | active |
| tests/unit/test_tool_registry.py | tests, unit, tool-registry, tdd | TDD unit tests for tool_registry.py: 6 tests covering health profile, guidance filtering, KB loading, file writing, meal insertion | active |
| bot/agents/weekly_report.py | agents, weekly-report, opus, langgraph | WeeklyReportAgent — thin BaseAgent subclass loading weekly_report.yaml; Opus model, 5 context blocks, no checkpointer | active |
| bot/agents/health_insights.py | agents, health-insights, opus, langgraph, checkpointer, multi-turn | HealthInsightsAgent — thin BaseAgent subclass loading health_insights.yaml; Opus model, 5 context blocks, use_checkpointer=True | active |
| tests/integration/test_weekly_report.py | tests, integration, weekly-report, tdd | Integration tests for WeeklyReportAgent: 10 tests covering instantiation, invocation, and context injection | active |
| tests/integration/test_health_insights.py | tests, integration, health-insights, checkpointer, tdd | Integration tests for HealthInsightsAgent: 11 tests covering instantiation, invocation, context injection, and tools | active |
| bot/agents/orchestrator.py | agents, orchestrator, langgraph, haiku, routing | Thin OrchestratorAgent wrapper — loads orchestrator.yaml via load_agent, delegates to BaseAgent | active |
| bot/agents/knowledge_ingestor.py | agents, knowledge-ingestor, langgraph, sonnet, pdf | Thin KnowledgeIngestorAgent wrapper — loads knowledge_ingestor.yaml via load_agent, delegates to BaseAgent | active |
| tests/integration/test_orchestrator.py | tests, integration, orchestrator, tdd | Integration tests for OrchestratorAgent: instantiation, invoke with text/nutrition question, empty health profile | active |
| tests/integration/test_knowledge_ingestor.py | tests, integration, knowledge-ingestor, tdd | Integration tests for KnowledgeIngestorAgent: instantiation, invoke with PDF state, save_to_knowledge_base tool file/schema checks | active |
| bot/agents/meal_analyzer.py | agents, meal, photo, langgraph, sonnet | MealAnalyzerAgent — thin BaseAgent wrapper for food photo analysis; loads meal_analyzer.yaml | active |
| bot/agents/health_extractor.py | agents, health, pdf, lab-report, langgraph, sonnet | HealthExtractorAgent — thin BaseAgent wrapper for lab PDF extraction; loads health_extractor.yaml | active |
| tests/integration/test_meal_analyzer.py | tests, integration, meal-analyzer, tdd | Integration tests for MealAnalyzerAgent — 11 tests, mock_anthropic, direct tool DB verification | active |
| tests/integration/test_health_extractor.py | tests, integration, health-extractor, tdd | Integration tests for HealthExtractorAgent — 10 tests, mock_anthropic, direct tool DB verification | active |
| bot/agents/daily_summary.py | agents, langgraph, haiku, daily-summary | DailySummaryAgent — BaseAgent subclass loaded from daily_summary.yaml, 3 context blocks injected | active |
| tests/integration/test_daily_summary.py | tests, integration, daily-summary, tdd | Integration tests for DailySummaryAgent: instantiation, no-meals, returns-messages, health profile context injection | active |
| tests/integration/test_pattern_detector.py | tests, integration, pattern-detector, tdd | Integration tests for PatternDetectorAgent: instantiation, returns-messages, escalation tier pure function, dedup via DB | active |
