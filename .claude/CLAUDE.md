# FitAi — Nutrition Tracker Bot

## What This Is
Standalone Telegram bot — personal dietary nutritionist for Sahil, targeting
lower A1C, lower LDL cholesterol, increased HDL, and physical fitness.
Single user. Not a general-purpose app.

Full spec: `docs/nutrition-tracker-design.md`
Architecture diagram: `docs/nutrition-tracker-design.html`

## Tech Stack
- Python 3.11+, python-telegram-bot v20+
- LangGraph v0.4+ + langchain-anthropic (multi-agent, DAG routing)
- Claude Opus 4.8 (`ANTHROPIC_MODEL_HEAVY`) — WeeklyReportAgent, HealthInsightsAgent
- Claude Sonnet 4.6 (`ANTHROPIC_MODEL_MID`) — MealAnalyzerAgent, HealthExtractorAgent, KnowledgeIngestorAgent
- Claude Haiku 4.5 (`ANTHROPIC_MODEL_FAST`) — OrchestratorAgent, PatternDetectorAgent, DailySummaryAgent, flows
- SQLite WAL mode — on-VM, single file at `SQLITE_DB_PATH`
- knowledge_base/ — JSON files, one per ingested research article (~6k tokens, always loaded in full)
- cachetools TTLCache — media buffer (2s), health profile (1hr)
- diskcache (SQLite-backed) — callout dedup (24hr), Fitbit token, onboarding flag
- Prefect v3+ — 6 scheduled flows, self-hosted on VM
- Uptime Kuma (Docker) — push monitor, bot pings every 5min, Telegram alert if down
- Monocle (`monocle-apptrace`) — auto-instruments LangGraph, writes traces to `/opt/nutrition-bot/logs/traces/` as JSON; download via gcloud scp to inspect offline
- Fitbit Web API — steps + sleep
- Open-Meteo — weather, no API key needed

## Agent Roster

| Agent | Model | Trigger | Pattern |
|---|---|---|---|
| OrchestratorAgent | Haiku | Every real-time message | Tool-call for context (conditional) |
| MealAnalyzerAgent | Sonnet | Photo(s) | Inject: health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base |
| HealthExtractorAgent | Sonnet | Lab report PDF | No context injection |
| KnowledgeIngestorAgent | Sonnet | Research article PDF | No context injection |
| PatternDetectorAgent | Haiku | After daily summary | No context injection |
| DailySummaryAgent | Haiku | 11:30pm Prefect | Inject: health_profile, user_profile, nutrition_guidance |
| WeeklyReportAgent | Opus | Sunday 8pm Prefect | Inject: health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base |
| HealthInsightsAgent | Opus | Symptom questions | Inject: health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base |

## Key Conventions
- All times in `America/Los_Angeles` via `zoneinfo` — never hardcode UTC offsets
- Tests are mandatory before implementation (TDD) — see spec Phase 2–6
- No image storage — photos analyzed on receipt, discarded immediately
- Single user — no `user_id` scoping needed anywhere in DB queries
- Web search never fires automatically — always request permission via `ask_web_search_permission` tool
- Pause-and-wait (permission requests, lab confirm) uses LangGraph `interrupt()` — not custom state
- All DB access goes through `db/queries.py` — never raw SQL in agents or flows
- `context:` in YAML = injected into system prompt; `tools:` = callable mid-run — don't mix these up

## File Layout
```
bot/agents/          — one file per agent, all use LangGraph StateGraph
bot/agents/configs/  — YAML config per agent (model, tools, context, triggers)
bot/handlers/        — Telegram update routing only, no business logic here
flows/               — Prefect @flow functions, one file per scheduled job
db/models.py         — SQLAlchemy models for all 10 tables
db/queries.py        — all shared query functions
db/migrations/       — SQL migration files
prompts/             — system prompt .txt files for each agent + morning_report
knowledge_base/      — JSON files from ingested research articles
```

## Database — 10 Tables
| Table | Grows? | Notes |
|---|---|---|
| meal_logs | Yes | One row per meal log |
| daily_health_logs | Yes | One row per day (Fitbit data) |
| user_profile | No (id=1) | Single row, set at onboarding |
| user_health_profile | Yes | One row per lab report upload |
| user_nutrition_guidance | Append | Active/inactive rows, never deleted — remark explains why inactive, can reactivate |
| user_semantic_memory | Replaced | Full replacement weekly (Sunday 6pm) |
| daily_summaries | Yes | One row per day |
| weekly_reports | Yes | One row per week |
| patterns | Yes | Streak tracking |
| indian_foods | Manual | Populated from IFCT/NIN data |

## Prefect Flows Schedule (America/Los_Angeles)
| Flow | Schedule | What it does |
|---|---|---|
| morning_report_flow | 10:30am daily | Fitbit + weather + Haiku Claude call |
| lunch_alert_flow | 3:00pm daily | SQL check → alert if no breakfast/lunch |
| dinner_alert_flow | 10:30pm daily | SQL check → alert if no dinner |
| daily_summary_flow | 11:30pm daily | DailySummaryAgent → PatternDetectorAgent → save to daily_summaries |
| semantic_extraction_flow | 6:00pm Sunday | 90-day window → extract facts → user_semantic_memory |
| weekly_report_flow | 8:00pm Sunday | WeeklyReportAgent → PatternDetectorAgent |

## Environment
- VM: e2-small, us-central1-a, project finance-assistant-476706
- SSH: `gcloud compute ssh nutrition-bot --project=finance-assistant-476706 --zone=us-central1-a --tunnel-through-iap`
- App root on VM: `/opt/nutrition-bot/`
- Secrets: `/opt/nutrition-bot/.env` — never commit this file
- Local dev: SQLite `:memory:` + tmp `knowledge_base/` dir (see `tests/conftest.py`)

## North Star
Every feature connects back to: reduce A1C, lower LDL, increase HDL, stay fit.
When in doubt about a design decision, ask: does this make Sahil healthier?
