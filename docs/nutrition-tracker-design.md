# Nutrition Tracker — Design Spec
**Date:** 2026-05-25
**Replaces:** `.claude/plans/jolly-whistling-nebula.md`

---

## Goal

**North star: Help Sahil reduce A1C, lower LDL cholesterol, increase HDL, and stay physically fit.**

Every feature in this tool exists to serve that goal. The bot is not just a meal logger — it is an active health accountability partner. It should:
- Make it effortless to log what Sahil eats so there are no gaps in the data
- Surface patterns and correlations between food choices and health markers
- Deliver personalized, actionable nudges (not generic advice) grounded in Sahil's actual logged history
- Keep Sahil on track toward his long-term health targets, not just report on the past

A standalone Telegram bot running on a new GCP VM acts as the delivery mechanism. Meal photos submitted through Telegram are analyzed using Claude's vision capabilities and turned into daily/weekly health insights and accountability. Every message, every nudge, every report should connect back to this north star.

---

## Architecture Overview

Two-process Python application sharing a local SQLite database:

```
Process 1: Bot (python-telegram-bot v20+)
  └── Handles all real-time Telegram interactions

Process 2: Prefect Flows (scheduled jobs)
  └── 5 Prefect flows with scheduling, retries, and observability

Shared:
  ├── SQLite (meal data, health profile, reports, LangGraph state)
  ├── knowledge_base/     (JSON files, one per ingested research article)
  ├── cachetools TTLCache  (in-memory: media group buffering, health profile)
  └── diskcache            (persistent local: callout dedup, Fitbit token)
```

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| Telegram | `python-telegram-bot` v20+ | Async, built-in JobQueue |
| Multi-agent | LangGraph v0.4+ + `langchain-anthropic` | DAG-based agent routing |
| LLM — heavy | Claude Opus 4.8 (`claude-opus-4-8`) | WeeklyReportAgent, HealthInsightsAgent |
| LLM — mid | Claude Sonnet 4.6 (`claude-sonnet-4-6`) | MealAnalyzerAgent, HealthExtractorAgent, KnowledgeIngestorAgent |
| LLM — fast | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | OrchestratorAgent, PatternDetectorAgent, DailySummaryAgent, flows |
| Web search | Claude built-in `web_search_20250305` | No extra API key |
| Database | SQLite (WAL mode) | On-VM, zero cost, single-user safe |
| In-memory cache | `cachetools` | Media group buffering (2s TTL), health profile cache |
| Persistent cache | `diskcache` (SQLite-backed) | Callout dedup (24hr TTL), Fitbit token rotation |
| Fitbit | Fitbit Web API | Existing developer app credentials |
| Weather | Open-Meteo (`openmeteo-requests`) | Free, no API key, no rate limit |
| Hosting | New GCP VM (`e2-small`) | ~$12/month |
| Scheduler | Prefect (open source, self-hosted) | Retries, observability, failure alerts |
| Monitoring | Uptime Kuma (self-hosted, Docker) | Bot heartbeat via push monitor → Telegram alert if down |
| Tracing | Monocle (`monocle-apptrace`) | Auto-instruments LangGraph; writes traces to local JSON files |
| Timezone | `zoneinfo` / `America/Los_Angeles` | All times in PST/PDT |
| ORM | SQLAlchemy 2.0+ | SQLite dialect |

**Total infra cost: ~$12/month** (e2-small only — no Cloud SQL)

**Dependencies:**
```
python-telegram-bot==20.*
langgraph>=0.4.0
langchain-anthropic
anthropic
sqlalchemy>=2.0
cachetools
diskcache
openmeteo-requests
prefect>=3.0
python-dotenv
pydantic>=2.0
zoneinfo
monocle-apptrace
```

---

## Multi-Agent Design

Meta-orchestrator pattern: an OrchestratorAgent receives all inputs, decides which specialist(s) to invoke, and can chain agents.

### Agent Roster

| Agent | Model | max_tokens | recursion_limit | Tools |
|---|---|---|---|---|
| `OrchestratorAgent` | Haiku 4.5 | 512 | 3 | Routes to specialists; handles general questions directly (`get_health_profile`, `get_user_profile`, `get_nutrition_guidance`, `query_knowledge_base`, `get_semantic_memory`, `send_telegram_msg`) |
| `MealAnalyzerAgent` | Sonnet 4.6 | 1024 | 5 | `ask_web_search_permission`, `save_meal_analysis` — context injected: health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base |
| `HealthExtractorAgent` | Sonnet 4.6 | 768 | 5 | `confirm_with_user`, `save_health_profile`, `generate_nutrition_guidance` |
| `PatternDetectorAgent` | Haiku 4.5 | 512 | 3 | `query_last_7_days`, `get_sent_callouts`, `send_telegram_msg` |
| `DailySummaryAgent` | Haiku 4.5 | 1536 | 3 | `query_todays_meals`, `send_telegram_msg` — context injected: health_profile, user_profile, nutrition_guidance |
| `WeeklyReportAgent` | Opus 4.8 | 3072 | 8 | `query_week_meals`, `get_last_week_recommendations`, `send_telegram_msg` — context injected: health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base |
| `HealthInsightsAgent` | Opus 4.8 | 1536 | 10 | `query_last_2_days_meals`, `query_last_2_days_steps`, `query_last_2_days_sleep`, `ask_web_search_permission`, `send_telegram_msg` — context injected: health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base |
| `KnowledgeIngestorAgent` | Sonnet 4.6 | 1536 | 3 | `save_to_knowledge_base` |

**Calibration note:** These are starting estimates with 50% buffer over expected output size. Check `response.usage.output_tokens` in logs after first week of real usage and adjust. If you see `stop_reason: "max_tokens"` for any agent, raise its limit.

### Agent Extensibility — YAML Config Pattern

Every agent is fully described by a YAML config file. Adding a new agent = drop a YAML file in `bot/agents/configs/`. No other code changes needed.

**Config schema:**
```yaml
name: MealAnalyzerAgent
model: claude-sonnet-4-6          # maps to ANTHROPIC_MODEL_MID
max_tokens: 1024
recursion_limit: 5
prompt: prompts/meal_analyzer.txt  # system prompt file
tools:
  - ask_web_search_permission
  - get_health_profile
  - get_semantic_memory
  - save_meal_analysis
context:                           # what gets injected into system prompt
  - health_profile
  - semantic_memory
  - knowledge_base
triggers:
  - photo                          # OrchestratorAgent uses this for routing
```

**AgentLoader** (`bot/agents/agent_loader.py`) — scans `configs/` at startup, builds `AGENT_REGISTRY`:
```python
AGENT_REGISTRY = {
    trigger: AgentLoader().load(config_path)
    for config_path in glob("bot/agents/configs/*.yaml")
    for trigger in config["triggers"]
}
```

**TOOL_REGISTRY** (`bot/agents/tool_registry.py`) — callable tools only (not injected context loaders):
```python
TOOL_REGISTRY = {
    # OrchestratorAgent — tool-call (conditional: only when answering directly)
    "get_health_profile":          get_health_profile,
    "get_user_profile":            get_user_profile,
    "get_nutrition_guidance":      get_nutrition_guidance,
    "get_semantic_memory":         get_semantic_memory,
    "query_knowledge_base":        query_knowledge_base,

    # HealthExtractorAgent — post-confirm actions
    "confirm_with_user":           confirm_with_user,
    "save_health_profile":         save_health_profile,
    "generate_nutrition_guidance": generate_nutrition_guidance,

    # Shared across multiple agents
    "save_meal_analysis":          save_meal_analysis,
    "query_last_7_days":           query_last_7_days,
    "query_todays_meals":          query_todays_meals,
    "query_week_meals":            query_week_meals,
    "query_last_2_days_meals":     query_last_2_days_meals,
    "query_last_2_days_steps":     query_last_2_days_steps,
    "query_last_2_days_sleep":     query_last_2_days_sleep,
    "get_last_week_recommendations": get_last_week_recommendations,
    "get_sent_callouts":           get_sent_callouts,
    "ask_web_search_permission":   ask_web_search_permission,
    "save_to_knowledge_base":      save_to_knowledge_base,
    "send_telegram_msg":           send_telegram_msg,
}

# Context loaders (for injection agents) are handled by AgentLoader, not TOOL_REGISTRY:
CONTEXT_LOADERS = {
    "health_profile":      load_health_profile,    # SELECT * ORDER BY report_date DESC LIMIT 1
    "user_profile":        load_user_profile,      # SELECT * FROM user_profile WHERE id=1
    "nutrition_guidance":  load_nutrition_guidance, # SELECT * FROM user_nutrition_guidance
    "semantic_memory":     load_semantic_memory,   # SELECT * FROM user_semantic_memory
    "knowledge_base":      load_knowledge_base,    # glob knowledge_base/*.json
}
```

**BaseAgent** (`bot/agents/base_agent.py`) — shared LangGraph wiring all agents inherit:
```python
class BaseAgent:
    def __init__(self, model, max_tokens, recursion_limit, prompt, tools):
        self.client = anthropic.Anthropic()
        self.graph = self._build_graph()

    def invoke(self, state: AgentState) -> AgentState: ...
    def _build_graph(self) -> StateGraph: ...
```

**To add a new agent in the future:**
1. Create `bot/agents/configs/exercise_tracker.yaml`
2. Create `bot/agents/exercise_tracker.py` (business logic only)
3. Register any new tools in `TOOL_REGISTRY`
4. App picks it up on next restart — Orchestrator routes to it automatically

### Context Injection vs Tool-call

Two ways an agent can access shared data:

| Pattern | How | When to use |
|---|---|---|
| **Injection** (`context:` in YAML) | Loaded from DB once, prepended to system prompt before the agent runs | Context is **always** consumed — injecting it unconditionally is cheaper than a tool-call round-trip |
| **Tool-call** (`tools:` in YAML) | Agent calls the tool mid-run, on demand | Context is **conditionally** needed — don't pay tokens when routing or task doesn't require it |

**Per-agent breakdown:**

| Agent | Pattern | Rationale |
|---|---|---|
| `MealAnalyzerAgent` | **Inject** health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base | Every meal is evaluated against targets and rules — context always consumed |
| `DailySummaryAgent` | **Inject** health_profile, user_profile, nutrition_guidance | Always flags meals against targets — no conditional logic needed |
| `WeeklyReportAgent` | **Inject** health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base | Full-picture analysis — always needs everything |
| `HealthInsightsAgent` | **Inject** health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base | Personalised symptom Q&A without profile context produces generic answers |
| `OrchestratorAgent` | **Tool-call** for profile/guidance | Routes most messages without needing context; only fetches when answering directly |
| `HealthExtractorAgent` | **None** | Extracts lab values from a PDF — user profile doesn't help Claude read a blood test |
| `KnowledgeIngestorAgent` | **None** | Pure document ingestion — no profile context changes how a research paper is summarised |
| `PatternDetectorAgent` | **None** | Streak detection uses hardcoded thresholds, not personalised lab values |

### What Agents See — Unified Context

The 4 injection agents receive these blocks prepended to their system prompt:

```
=== USER PROFILE ===
Name: Sahil, Age: 33, Gender: Male
Height: 178cm, Weight: 81kg, BMI: 25.6
Diet: omnivore
Allergies: none  |  Intolerances: none
Avoided foods: none
Preferred cuisines: indian, mediterranean
Activity level: moderate
Goals: 10,000 steps/day, 7hrs sleep

Macro targets: 1,800 kcal · 140g protein · 180g carbs · 60g fat · 30g fiber

=== LATEST LAB RESULTS (2026-05-15) ===
A1C: 6.4%  (target: <5.7%)
LDL: 142 mg/dL  (target: <100)
HDL: 48 mg/dL  (target: >60)
Triglycerides: 180 mg/dL
Medications: metformin 500mg

=== PERSONALISED NUTRITION RULES ===
[a1c] Limit refined carbs to 45g/meal — A1C 6.4% indicates pre-diabetic range
[a1c] Prioritise high-fiber foods (>8g/meal) — fiber slows glucose absorption
[ldl] Saturated fat cap: 15g/day — LDL 142 is 42% above target
[ldl] Favour unsaturated fats: avocado, nuts, olive oil over ghee/butter
[hdl] Include omega-3 sources 3×/week — salmon, flax, walnuts raise HDL
[general] Avoid sugary beverages — direct A1C impact

=== SEMANTIC MEMORY (as of 2026-06-01) ===
• Breakfast is skipped ~3x/week, most often Monday and Tuesday
• High-GI meals cluster on weekday evenings (likely eating out)
• Steps average 8,200 on weekends vs 3,100 on weekdays
• Dietary score drops 20+ points when rajma or chole is included
```

**Null handling:** If any section is missing (no lab report yet, no profile set, no semantic memory), agents inject a one-line fallback and proceed. No agent crashes on missing context.

---

### Web Search Policy

**Web search never fires automatically.** Any agent that needs web context must first send a permission request via Telegram:

> "I'd like to search the web for [specific reason — e.g. nutritional profile of taro root]. Can I?"

Only after explicit user confirmation does the search proceed. This applies to all agents. The `ask_web_search_permission` tool handles this pause-and-wait pattern before `web_search` is called.

**Pause-and-wait implementation — LangGraph `interrupt()`:**

Both `ask_web_search_permission` and `confirm_with_user` (HealthExtractorAgent) use LangGraph's built-in interrupt/resume. No custom state machine needed — `AsyncSqliteSaver` (already in the spec) is the checkpointer that holds state between the pause and the resume.

```python
def ask_web_search_permission(reason: str) -> str:
    # Pauses graph, sends message to user, saves state to AsyncSqliteSaver checkpoint
    answer = interrupt(f"I'd like to search the web for {reason}. Can I?")
    return answer  # resumes here when user replies

def confirm_with_user(message: str) -> str:
    answer = interrupt(message)  # same pattern
    return answer
```

When the user replies, the bot handler resumes the graph:
```python
# in bot/handlers — on any text message from user
graph.invoke(Command(resume=user_message), config={"thread_id": chat_id})
```

The `thread_id` (keyed to Telegram `chat_id`) is what links the incoming reply to the paused graph state in the checkpoint.

---

### Orchestrator Routing Logic

The OrchestratorAgent handles **real-time Telegram messages only**. Scheduled jobs (daily summary, weekly report, morning briefing, alerts) are triggered directly by Prefect flows — they bypass the Orchestrator entirely.

```
Real-time input → Specialist(s)
─────────────────────────────────────────────────
Photo(s)          → MealAnalyzerAgent
                    → PatternDetectorAgent (after meal saved)
PDF document      → HealthExtractorAgent (lab report)
                    → KnowledgeIngestorAgent (research article)
                    [OrchestratorAgent classifies via Claude]
Health question   → HealthInsightsAgent (conversational, multi-turn)
General question  → OrchestratorAgent answers directly (uses health profile + knowledge base)
Text command      → Rule-based handler (no agent)
```

```
Scheduled triggers (Prefect flows → agents directly, no Orchestrator)
─────────────────────────────────────────────────
morning_report_flow   → Fitbit + Open-Meteo + Claude (no LangGraph agent)
lunch_alert_flow      → SQL check → Telegram if no breakfast/lunch logged
dinner_alert_flow     → SQL check → Telegram if no dinner logged
daily_summary_flow    → DailySummaryAgent → PatternDetectorAgent
weekly_report_flow    → WeeklyReportAgent → PatternDetectorAgent (7-day)
```

### LangGraph State

```python
class AgentState(TypedDict):
    input_type: str          # "photo" | "pdf" | "command" | "cron"
    telegram_chat_id: int
    messages: list
    media_group_id: str | None
    photos: list             # buffered from cachetools TTLCache (2s window)
    analysis_result: dict | None
    next_agent: str | None
```

LangGraph checkpointer: `AsyncSqliteSaver` — survives bot restarts, zero extra infrastructure.

---

## Feature Specs

### 1. Meal Photo Logging

**Multi-photo handling (media groups):**
- Telegram sends album photos as separate messages with shared `media_group_id`
- On photo receipt: store in `media_buffer` TTLCache under key `media_group:{id}` (2s TTL)
- Trigger: first photo schedules `asyncio.get_event_loop().call_later(2, process_group, media_group_id)` — fires after 2s, reads all buffered photos, processes as one meal
- Single meal-type prompt sent regardless of number of photos

**Meal type selection:**
- Always show inline keyboard: `[Breakfast] [Lunch] [Dinner] [Snack]`
- No caption parsing, no time-based inference — always explicit

**Non-food detection:**
- `MealAnalyzerAgent` first classifies: is this food/beverage?
- If not food: reply "That doesn't look like food — did you mean to send this?" with `[Yes, analyze anyway] [Discard]`
- If food: proceed to nutrition analysis

**Beverages:**
- Explicitly included in analysis — drinks photographed as part of a meal are identified, macros estimated, sugar/alcohol flagged for A1C relevance

**Acknowledgment:** "Got it! Your [lunch] has been logged 📷"

**Analysis output (stored in SQLite, not sent to user):**
```json
{
  "foods_identified": ["white rice", "chicken curry", "chai"],
  "estimated_macros": {
    "calories": 780,
    "protein_g": 38,
    "carbs_g": 95,
    "fat_g": 22,
    "fiber_g": 3,
    "saturated_fat_g": 8,
    "sugar_g": 12
  },
  "glycemic_load": "high",
  "cholesterol_flags": ["saturated fat above target"],
  "a1c_flags": ["high glycemic load", "sugary beverage"],
  "score": 48
}
```

---

### 2. Health Profile Upload

**Flow:**
1. User sends a PDF lab report to the bot
2. `HealthExtractorAgent` extracts: A1C, LDL, HDL, triglycerides, medications, targets, BMI/weight
3. Bot replies with extracted values for confirmation:
   > "I found: A1C: 6.2%, LDL: 142 mg/dL, HDL: 48 mg/dL, Triglycerides: 180 mg/dL. Does this look right?"
   > `[Confirm] [Re-upload]`
4. On confirm: save/overwrite `user_health_profile` table
5. On re-upload: discard and wait for new PDF

**Health context in every LLM call:**
- System prompt for all agents prepends extracted health values
- Recommendations are personalized to actual A1C/cholesterol targets

**Null state (no profile uploaded yet):**
- `get_health_profile` returns `None` when the table is empty (no row with id=1)
- All agents handle `None` by injecting a fallback context: *"No lab report uploaded yet — recommendations are general until Sahil uploads his first report."*
- On first non-photo, non-PDF message from the user, the bot appends a one-time prompt: *"📋 Tip: send me your latest lab report PDF and I'll personalise everything to your actual A1C and cholesterol values."*
- This prompt fires only once (tracked via diskcache key `onboarding_prompt_sent`).

---

### 3. Morning Briefing (10:30am PST daily)

Simple Prefect flow — one Claude call to format the report, no LangGraph agent. Model: `ANTHROPIC_MODEL_FAST` (Haiku 4.5).

**Content:**
- Steps walked yesterday (Fitbit API: `/activities/date/{yesterday}`)
- Sleep duration for last night (Fitbit API: `/sleep/date/{today}`, data from midnight)
- Weather for zipcode 94043 / Mountain View, CA (Open-Meteo: lat 37.3861, lon -122.0839 — no API key)
- Rain window: if rain expected, include time range (e.g., "Rain expected 2pm–5pm") — omit entirely if no rain
- Quote (Claude generated, alternates by day): even days → Bhagavad Gita verse + brief context; odd days → tech/business leader quote

**Steps nudge:** If yesterday's steps were under 5,000, append a motivational callout to the morning report. Omit if steps ≥ 5,000.

**Sleep nudge:** If last night's sleep was under 7 hours, append a callout noting the shortfall and its impact. Omit if sleep ≥ 7 hours.

**Example message (odd day — tech quote):**
```
Good morning! ☀️

🚶 Steps yesterday: 2,100 / 10,000
⚠️ Under 5,000 steps yesterday — a 20-min walk today makes a real
   difference for your A1C and energy levels.
😴 Sleep last night: 5h 30min
⚠️ Under 7 hours of sleep — poor sleep raises cortisol and directly
   impacts blood sugar. Try to get to bed earlier tonight.
🌤 Mountain View: 68°F, partly cloudy
🌧 Rain expected: 3pm – 6pm

"The only way to do great work is to love what you do." — Steve Jobs
```

**Example message (even day — Gita quote):**
```
Good morning! ☀️

🚶 Steps yesterday: 7,240 / 10,000
😴 Sleep last night: 7h 45min
🌤 Mountain View: 68°F, partly cloudy

🕊 "You have a right to perform your prescribed duties, but you are
   not entitled to the fruits of your actions." — Bhagavad Gita 2.47
```

**Prompt** (`prompts/morning_report.txt`):

**System:**
```
You are a personal health accountability partner sending a daily morning briefing via Telegram.

Write a warm, concise morning message using the data provided. Follow this structure exactly, in order:

1. Greeting: "Good morning! ☀️"
2. Steps: "🚶 Steps yesterday: {steps} / {goal}"
   - If steps < 5,000: add ⚠️ nudge on next line — motivational, connect to A1C or energy. One sentence.
   - If steps ≥ 5,000: no nudge.
3. Sleep: "😴 Sleep last night: {hours}h {mins}min"
   - If sleep < 7hrs: add ⚠️ nudge on next line — mention cortisol or blood sugar impact. One sentence.
   - If sleep ≥ 7hrs: no nudge.
4. Weather: "🌤 {location}: {temp}°F, {condition}"
   - If rain_expected: add "🌧 Rain expected: {rain_window}" on next line.
   - If no rain: omit this sub-line entirely.
5. Quote:
   - day_type "gita":  🕊 "[verse]" — Bhagavad Gita [chapter.verse]  (add one-line context below)
   - day_type "tech":  "[quote]" — [Name]

Rules: Warm and human. No extra sections. No bullet walls. Vary phrasing day to day.
```

**User message** (populated by the flow before calling Claude):
```
steps_yesterday: {steps}
step_goal: {goal}
sleep_hrs: {sleep_hrs}
location: Mountain View, CA
temp_f: {temp}
weather_condition: {condition}
rain_expected: {true|false}
rain_window: {window or "none"}
day_type: {gita|tech}
```

---

### 4. Missed Meal Alerts

Two daily cron checks (same `alerts.py` script, called twice):

| Time | Check | Message |
|---|---|---|
| 3:00pm PST | Breakfast OR lunch not logged | "Hey! You haven't logged breakfast or lunch yet 🍽" |
| 10:30pm PST | Dinner not logged | "Dinner time — snap a photo before you sleep! 🍽" |

Alert is skipped if the meal has already been logged for that day.

---

### 5. Daily Meal Summary (11:30pm PST)

`DailySummaryAgent` aggregates all meals logged today and sends:
- All meals logged with foods identified
- Total daily macros (calories, protein, carbs, fat, fiber, saturated fat, sugar)
- A1C risk foods consumed + alternatives
- Cholesterol risk items flagged
- Daily dietary score (0–100)
- One concrete improvement for tomorrow

Steps and sleep are **not** included in the daily summary.

---

### 6. Pattern Detection

Runs after each daily summary (Sunday report also triggers it for 7-day patterns).

**Patterns tracked:**
| Pattern | Threshold | Message style |
|---|---|---|
| High glycemic load | ≥3 consecutive days | Escalating daily once triggered |
| Saturated fat above target | ≥3 consecutive days | Escalating daily |
| Skipped meals | ≥3 consecutive days | Escalating daily |
| Steps below 5,000 | ≥3 consecutive days | Escalating daily |
| Sleep under 6hrs | ≥3 consecutive days | Escalating daily |

**Deduplication:** diskcache key `callout:{date}:{pattern_type}` with 24hr TTL prevents same-day duplicate sends.

**Escalation:** Tone and urgency increase with streak length. Three tiers:

| Streak | Tone | What changes |
|---|---|---|
| Day 3 | Informational | Flags the pattern, states the health connection calmly |
| Days 4–6 | Firm | Stronger language, explicit impact on A1C/cholesterol goal |
| Day 7+ | Strong health warning | Direct, urgent — includes a clear note to take care of your health |

Example for "high glycemic load" pattern:
```
Day 3:  "You've had high glycemic load meals 3 days in a row 🍚 — this is
         starting to work against your A1C target."

Day 5:  "5 consecutive days of high glycemic load ⚠️ — this is directly
         stalling your A1C recovery. Your body needs a break from the sugar
         spikes. Make a change today."

Day 7+: "7 days of high glycemic load in a row 🚨 — this is a serious
         pattern that is putting real stress on your blood sugar. Please
         take care of your health. One better meal today is how streaks
         end — start there."
```

**Delivery:** Random offset between 8:00am–11:00am PST next morning (feels organic, not robotic).

---

### 7. General Conversation

Handles any text input the Orchestrator doesn't classify as a health symptom question, command, or known trigger.

**Behaviour:**
- Answers freely using Claude — general knowledge, food facts, recipes, health concepts, curiosity questions
- Has access to `get_health_profile` and `query_knowledge_base` — so answers are personalised where relevant (e.g. "is ghee bad for me?" uses your actual LDL values)
- For questions completely outside health/general knowledge scope (e.g. "write my CV", "debug this code"), responds warmly:
  > "That's a bit outside what I'm built for 😄 — but I'm great at nutrition, health questions, or analysing your meals! What can I help you with?"

**Orchestrator classification:**
The Orchestrator distinguishes between `general_question` and `health_question` based on whether the input references personal symptoms, feelings, or the user's own body. Personal health questions (e.g. "why am I tired?") are routed to `HealthInsightsAgent`. General questions (e.g. "is oat milk good for cholesterol?") are answered directly by the Orchestrator using health profile and knowledge base context.

**Example exchanges:**
```
User: is brown rice better than white rice for diabetics?
Bot: Yes! 🌾 Brown rice has a glycemic index of ~50 vs white rice at ~72.
     Given your A1C target, swapping to brown rice 3x a week is one of
     the easiest wins you can make. It also has 3x more fiber which slows
     glucose absorption. Want me to flag white rice in your meal analysis? 😊

User: what's the capital of France?
Bot: Paris! 🗼 Though I'm much better at telling you what to eat than
     geography trivia 😄 — ask me anything about your nutrition or health!
```

---

### 8. Health Insights Q&A

Triggered when the OrchestratorAgent detects a natural language health symptom question — e.g., "why am I feeling low energy?", "why am I bloated?", "why do I feel gassy today?".

**Conversational flow:**
1. `HealthInsightsAgent` receives the question
2. Queries last 2 days of meal logs, steps, and sleep from SQLite
3. Asks one focused follow-up question to narrow down the cause:
   > "Has this been going on since this morning or did it start yesterday?"
   > "Did you eat anything unusual yesterday or today?"
4. Incorporates the user's answer + data to form a personalised explanation
5. Uses `web_search` to validate correlations (e.g., high FODMAP foods → bloating, low sleep + low steps → fatigue)
6. Delivers a clear, evidence-based answer citing specific meals/metrics from the last 2 days

**Lookback window:** Always 2 days (today + yesterday).

**Data queried:**
- `meal_logs` — foods identified, macros, glycemic load, flags
- `daily_health_logs` — steps, sleep duration, sleep quality
- `user_health_profile` — A1C, LDL, medications (for context)

**Example exchange:**
```
User: why am I feeling so gassy today?

Bot: Let me check your last 2 days. Quick question — did the bloating
     start after a specific meal, or has it been all day?

User: after lunch today

Bot: Your lunch today included rajma (kidney beans) and cauliflower —
     both high-FODMAP foods that are common gas triggers, especially
     combined. Yesterday you also had dal, so you've had two consecutive
     high-legume days with limited fiber spacing. Try peppermint tea and
     avoid legumes at dinner tonight.
```

**Conversation state:** Stored in LangGraph checkpoint (SQLite via `AsyncSqliteSaver`) per chat session so the agent remembers the follow-up answer within the same conversation.

---

### 9. Weekly Report (Sunday 8pm PST)

`WeeklyReportAgent` generates a full weekly picture:

- Week-over-week dietary score delta
- Worst dietary patterns of the week
- Avg daily steps + trend (improving/declining)
- Avg sleep duration + quality trend
- **Recommendation follow-through**: compares last week's stored recommendations against this week's `foods_identified` arrays — Claude evaluates each recommendation as followed / partially followed / not followed with evidence
- Correlations (e.g., "Your worst dietary days overlapped with your lowest step counts")
- **Honest verdict:** one warm but direct sentence summarising the week's trajectory relative to A1C/cholesterol goals — e.g. *"Overall a step forward — fewer high-GI days than last week, though sleep is still your biggest wildcard 🎯"* or *"Tough week nutritionally — three days of high saturated fat puts your LDL trend in the wrong direction 😬. Next week is a fresh start."*
- 3 specific ranked changes for next week

**Week 1 exception:** Skip the recommendation follow-through section — no previous week data exists.

**On-demand skip:** If user sends `"skip comparison"` before Sunday, the `weekly_reports` table is flagged and WeeklyReportAgent omits that section.

---

### 10. Episodic → Semantic Memory Extraction (Sunday 6pm PST)

Runs via `semantic_extraction_flow` at 6pm Sunday — 2 hours before the weekly report — so `WeeklyReportAgent` benefits from freshly extracted semantic facts.

**What it does:**
- Queries last 90 days of `meal_logs`, `daily_health_logs`, and `patterns`
- Claude analyzes the full window and extracts behavioural facts grouped by category
- Upserts all facts into `user_semantic_memory` (replaces stale facts with updated ones)

**Categories extracted:**
| Category | Example fact |
|---|---|
| `meal_pattern` | "Consistently eats high-GI meals on weekday evenings" |
| `meal_pattern` | "Breakfast is skipped ~3x per week, most often Monday and Tuesday" |
| `sleep_pattern` | "Sleep duration drops below 6hrs when dietary score < 50 the prior day" |
| `activity_pattern` | "Steps average 8,200 on weekends vs 3,100 on weekdays" |
| `behavioral` | "Saturday meals score 25+ points higher than weekday average" |
| `behavioral` | "High-saturated-fat meals cluster on Thursday–Friday" |

**Agents that use semantic memory (`get_semantic_memory` tool):**
- `WeeklyReportAgent` — grounds long-term trend analysis beyond the current week
- `HealthInsightsAgent` — richer context for symptom questions ("you tend to skip breakfast on the days you report low energy")
- `OrchestratorAgent` — personalises general Q&A answers
- `MealAnalyzerAgent` — flags meals that match known personal risk patterns

**Starts being meaningful:** after ~4 weeks of data. Before that, `get_semantic_memory` returns empty and agents fall back to raw recent data only.

### 11. User Onboarding

Triggered on first message from the user when `user_profile` row doesn't exist (checked at startup via diskcache key `onboarding_complete`).

**Flow:**
The bot sends a short conversational setup before processing any other request. Uses inline keyboards where possible to keep it frictionless:

```
Bot: Hey Sahil! 👋 Let me personalise your experience with a few quick questions.

     What's your diet type?
     [🥩 Omnivore]  [🥦 Vegetarian]  [🌱 Vegan]

Bot: Any food allergies or things you strictly avoid?
     (Type them comma-separated, or tap 'None')
     [None]

Bot: What's your typical activity level?
     [🪑 Sedentary]  [🚶 Moderate]  [🏃 Active]

Bot: Last one — what's your daily calorie target?
     [1,600 kcal]  [1,800 kcal]  [2,000 kcal]  [Skip for now]
```

On completion: save all answers to `user_profile`. Set diskcache key `onboarding_complete = True`.

**What gets populated:** `diet_type`, `allergies`, `avoided_foods`, `activity_level`, `calorie_target`. Everything else (`height_cm`, `weight_kg`, `preferred_cuisines`, macro breakdowns) defaults to `NULL` and is refined via `/profile update`.

**Skip / resume:** If user sends a non-answer (e.g. sends a photo mid-onboarding), save partial answers and continue after that interaction completes.

**`/profile update`:** Lets user update specific fields post-onboarding:
```
/profile update → bot sends current values + "What would you like to change?"
User: "change my calorie target to 2000"
Bot: "Done! Updated calorie target to 2,000 kcal. 👍"
```

---

## Knowledge Base

### Overview

Two knowledge sources ground the agent recommendations in facts rather than LLM guesses:

1. **Peer-reviewed research** (PDFs ingested by user) — dietary interventions for A1C, LDL, HDL; moderation guidelines; health frameworks. Stored as JSON files, one per article.
2. **Indian food nutrition table** — structured macros and glycemic index for Indian dishes Claude has limited training data on. Stored as a plain SQLite table, queried by food name.

**Context injection flow:**
```
Agent needs context
      │
      ├─► SQL lookup → indian_foods table (food name match)
      │
      └─► Load all JSON files from knowledge_base/ directory
            (~10-20 files, ~6,000 tokens total — always full coverage)
            │
            ▼
      All findings + health profile + meal data → Claude → personalised advice
```

### Indian Food Nutrition Table

Structured lookup — not a vector store. When `MealAnalyzerAgent` identifies an Indian dish, it queries this table for accurate macros instead of relying on Claude's estimates.

```sql
CREATE TABLE indian_foods (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,   -- e.g. "dal makhani", "tawa roti"
    calories_per_100g   REAL,
    protein_g           REAL,
    carbs_g             REAL,
    fat_g               REAL,
    fiber_g             REAL,
    saturated_fat_g     REAL,
    sugar_g             REAL,
    glycemic_index      INTEGER,
    notes               TEXT                -- e.g. "varies with ghee quantity"
);
```

Populated manually from trusted sources (IFCT, NIN India) before deployment. Editable via a simple `/addfood` command later.

### Research Article Ingestion

Triggered when user sends a PDF that is **not** a lab report. The `OrchestratorAgent` distinguishes via Claude classification.

`KnowledgeIngestorAgent` flow:
1. Extract full text from PDF
2. Claude identifies 10-20 key findings from the paper (LLM reasoning, no special tool)
3. Claude assigns relevance tags from a fixed set: `a1c`, `ldl`, `hdl`, `glycemic_index`, `fiber`, `saturated_fat`, `sleep`, `steps`, `inflammation`, `indian_foods`
4. Write JSON file to `knowledge_base/` directory (filename derived from PDF name)
5. Confirm to user: "📚 Ingested *Effect of dietary fiber on A1C* — 14 findings saved."

**Re-ingestion:** Sending the same PDF overwrites the existing JSON file.

### Knowledge Base File Format

```
knowledge_base/
  harvard-dietary-fiber-a1c-2023.json
  ldl-mediterranean-diet-2024.json
  indian-glycemic-index-guide-2022.json
```

Each file:
```json
{
  "source": "Effect of dietary fiber on A1C - Harvard 2023",
  "ingested_at": "2026-05-30",
  "relevance_tags": ["a1c", "fiber", "glycemic_index"],
  "findings": [
    "Dietary fiber intake >25g/day reduces A1C by 0.5–1.2% over 12 weeks",
    "Soluble fiber (oats, legumes) has stronger effect than insoluble fiber",
    "Each 5g/day fiber increase correlates with ~0.1% A1C reduction"
  ]
}
```

### Loading at Query Time

```python
def query_knowledge_base() -> list[dict]:
    kb_dir = Path("/opt/nutrition-bot/knowledge_base")
    return [json.loads(f.read_text()) for f in kb_dir.glob("*.json")]
```

All files are loaded and injected into the agent's system prompt as "relevant research findings." No retrieval step — full coverage guaranteed.

### Reasoning with Health Results

```
User's A1C: 6.4%  (from health profile)
User's meals: high GI 4 of last 7 days  (from meal_logs)
Research finding: "Reducing refined carbs lowers A1C by 0.5% over 3 months"  (from knowledge_base)
─────────────────────────────────────────────────────────────────────────────
Claude output: "Based on your current A1C and recent meal pattern, cutting
white rice 3x/week could realistically move your A1C from 6.4% toward 5.9%
within 3 months, consistent with [source]."
```

---

## SQLite Schema

SQLite WAL mode enabled at connection time: `PRAGMA journal_mode=WAL` — allows concurrent reads from bot + Prefect processes while serialising writes safely.

```sql
-- Daily Fitbit data: persisted by morning_report_flow each day
CREATE TABLE daily_health_logs (
    date                TEXT PRIMARY KEY,   -- ISO date: '2026-05-30'
    steps               INTEGER,
    steps_goal          INTEGER NOT NULL DEFAULT 10000,
    sleep_duration_hrs  REAL,
    sleep_quality       TEXT,               -- 'poor' (<6hrs) / 'fair' (6-7hrs) / 'good' (≥7hrs)
    fetched_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Meal logs: multiple entries per meal type per day supported
CREATE TABLE meal_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,         -- ISO date
    meal_type        TEXT NOT NULL,         -- breakfast/lunch/dinner/snack
    logged_at        TEXT NOT NULL,
    foods_identified TEXT,                  -- JSON array
    macros           TEXT,                  -- JSON object
    flags            TEXT,                  -- JSON object
    score            INTEGER
);

-- Static user profile: single row, manually set during onboarding, updated via /profile update
CREATE TABLE user_profile (
    id                  INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    name                TEXT,
    age                 INTEGER,
    gender              TEXT,
    height_cm           REAL,
    weight_kg           REAL,
    diet_type           TEXT,        -- 'omnivore' | 'vegetarian' | 'vegan'
    allergies           TEXT,        -- JSON array: ['peanuts', 'shellfish']
    intolerances        TEXT,        -- JSON array: ['lactose', 'gluten']
    avoided_foods       TEXT,        -- JSON array: ['alcohol', 'beef']
    preferred_cuisines  TEXT,        -- JSON array: ['indian', 'mediterranean']
    activity_level      TEXT,        -- 'sedentary' | 'moderate' | 'active'
    calorie_target      INTEGER,
    protein_target_g    INTEGER,
    carb_target_g       INTEGER,
    fat_target_g        INTEGER,
    fiber_target_g      INTEGER,
    step_goal           INTEGER DEFAULT 10000,
    sleep_goal_hrs      REAL    DEFAULT 7.0,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Health profile: one row per lab report upload — accumulates over time as new reports arrive
-- Agents query most recent row (ORDER BY report_date DESC LIMIT 1)
-- History preserved for trend analysis (WeeklyReportAgent, HealthInsightsAgent)
CREATE TABLE user_health_profile (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date     TEXT NOT NULL UNIQUE,   -- ISO date: '2026-05-30' — enforces one row per visit
    a1c             REAL,
    a1c_target      REAL,
    ldl             INTEGER,
    ldl_target      INTEGER,
    hdl             INTEGER,
    triglycerides   INTEGER,
    medications     TEXT,                   -- JSON array
    bmi             REAL,
    uploaded_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Insert pattern: INSERT INTO user_health_profile (report_date, a1c, ...) VALUES (?, ?, ...)
-- Query current: SELECT * FROM user_health_profile ORDER BY report_date DESC LIMIT 1
-- Query trend:   SELECT report_date, a1c, ldl, hdl FROM user_health_profile ORDER BY report_date

-- Personalised nutrition rules: append-with-status, rules are never deleted
-- Active rules: WHERE is_active = 1
-- When a lab update makes a rule obsolete: set is_active=0, remark='why', deactivated_at=now
-- When a previously deactivated rule becomes relevant again: set is_active=1, remark=NULL, deactivated_at=NULL
CREATE TABLE user_nutrition_guidance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule            TEXT NOT NULL,           -- "Limit carbs to 45g/meal given A1C 6.4%"
    category        TEXT NOT NULL,           -- 'a1c' | 'ldl' | 'hdl' | 'weight' | 'general'
    source          TEXT,                    -- 'health_profile' | 'knowledge_base'
    priority        INTEGER DEFAULT 1,
    is_active       INTEGER NOT NULL DEFAULT 1,
    remark          TEXT,                    -- why deactivated (NULL when active)
    source_lab_date TEXT,                    -- report_date of the lab that created this rule
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    deactivated_at  TEXT
);
-- Update pattern (on lab confirm): HealthExtractorAgent runs 3 steps via LLM comparison:
--   1. Deactivate rules no longer supported by new lab values (set is_active=0, add remark)
--   2. Reactivate previously deactivated rules now relevant again (set is_active=1, clear remark)
--   3. Insert genuinely new rules as active rows
-- Query current guidance: SELECT rule, category FROM user_nutrition_guidance WHERE is_active = 1

-- Daily summaries
CREATE TABLE daily_summaries (
    date            TEXT PRIMARY KEY,       -- ISO date
    total_macros    TEXT,                   -- JSON object
    dietary_score   INTEGER,
    improvements    TEXT,                   -- JSON array: [{category, recommendation, foods_to_watch}]
    sent_at         TEXT
);

-- Weekly reports
CREATE TABLE weekly_reports (
    week_start          TEXT PRIMARY KEY,   -- ISO date (Monday)
    avg_dietary_score   INTEGER,
    score_delta         INTEGER,
    patterns_detected   TEXT,               -- JSON array
    recommendations     TEXT,               -- JSON object (for follow-through comparison)
    skip_comparison     INTEGER DEFAULT 0,  -- 0/1 boolean
    sent_at             TEXT
);

-- Pattern callouts (for escalation tracking)
CREATE TABLE patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,          -- ISO date
    pattern_type    TEXT NOT NULL,
    streak_days     INTEGER NOT NULL,
    sent_at         TEXT
);

-- Semantic memory: extracted behavioural facts, refreshed weekly
CREATE TABLE user_semantic_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,  -- 'meal_pattern' | 'sleep_pattern' | 'activity_pattern' | 'behavioral'
    fact        TEXT NOT NULL,  -- human-readable extracted fact
    confidence  TEXT NOT NULL,  -- 'strong' | 'moderate' | 'weak'
    evidence    TEXT,           -- JSON: data points that support this fact
    valid_from  TEXT NOT NULL,  -- ISO date: earliest data this is drawn from
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for frequently-queried columns
CREATE INDEX idx_meal_logs_date ON meal_logs(date);
CREATE INDEX idx_patterns_date_type ON patterns(date, pattern_type);
```

---

## Caching Strategy

No Redis. Three layers, each sized to the use case:

### cachetools TTLCache (in-memory, lost on restart — acceptable)

| Cache | TTL | Purpose |
|---|---|---|
| `media_buffer` | 2s | Buffer photos from same Telegram album before processing |
| `health_profile` | 1hr | Avoid repeated SQLite reads across agents in same flow run |

```python
from cachetools import TTLCache
media_buffer  = TTLCache(maxsize=100, ttl=2)
profile_cache = TTLCache(maxsize=1,   ttl=3600)
```

### diskcache (SQLite-backed, survives restarts — required)

| Key | TTL | Purpose |
|---|---|---|
| `callout:{date}:{pattern_type}` | 24hr | Prevent duplicate pattern callouts same day |
| `fitbit_token` | None | Latest Fitbit refresh token (rotates on each API call) |

```python
import diskcache
cache = diskcache.Cache('/opt/nutrition-bot/.cache')
```

### SQLite (LangGraph checkpointing — structured, persistent)

LangGraph `AsyncSqliteSaver` writes agent conversation state to the main SQLite DB.
Used exclusively by `HealthInsightsAgent` for multi-turn Q&A sessions.

---

## Prefect Flows Schedule

All flows use `CronSchedule` with `timezone="America/Los_Angeles"`. Each flow has:
- **Retries**: 3 attempts with 60s delay (handles transient Fitbit/Claude/Telegram API failures)
- **Failure hook**: sends a Telegram message if all retries are exhausted
- **Observability**: all runs visible in Prefect UI dashboard

```python
@flow(retries=3, retry_delay_seconds=60)
def morning_report_flow(): ...

@flow(retries=3, retry_delay_seconds=60)
def lunch_alert_flow(): ...

@flow(retries=3, retry_delay_seconds=60)
def dinner_alert_flow(): ...

@flow(retries=3, retry_delay_seconds=60)
def daily_summary_flow(): ...

@flow(retries=3, retry_delay_seconds=60)
def semantic_extraction_flow(): ...

@flow(retries=3, retry_delay_seconds=60)
def weekly_report_flow(): ...
```

| Flow | Schedule | Timezone |
|---|---|---|
| `morning_report_flow` | `30 10 * * *` (10:30am) | America/Los_Angeles |
| `lunch_alert_flow` | `0 15 * * *` (3:00pm) | America/Los_Angeles |
| `dinner_alert_flow` | `30 22 * * *` (10:30pm) | America/Los_Angeles |
| `daily_summary_flow` | `30 23 * * *` (11:30pm) | America/Los_Angeles |
| `semantic_extraction_flow` | `0 18 * * 0` (6:00pm Sunday) | America/Los_Angeles |
| `weekly_report_flow` | `0 20 * * 0` (8:00pm Sunday) | America/Los_Angeles |

**Backups:** No backup flow in code. Use GCP disk snapshots scheduled from the GCP console — zero code, ~$0.05/GB/month, covers the entire VM disk including SQLite DB and knowledge base JSON files.

Prefect server runs as a `systemd` service alongside the bot process.

---

## Message Tone & Style

All outbound Telegram messages must:
- Include relevant emojis throughout — never feel dry or robotic
- Use a warm, conversational tone — like a knowledgeable friend, not a clinical report
- Be concise but human — avoid bullet-point walls of text
- Vary phrasing across days so messages don't feel repetitive

Example ✅: "Great job logging all three meals today! 🎉 Your dietary score is 72/100 — solid, but that naan at lunch was doing your A1C no favours 😅. Tomorrow: try swapping it for a small roti."

Example ❌: "Daily Score: 72. Flags: refined carbs. Recommendation: reduce naan."

---

## Bot Commands

| Command / Message | Action |
|---|---|
| Send photo(s) | Trigger meal logging flow |
| Send PDF | Trigger health profile extraction or research article ingestion |
| `"skip comparison"` | Flag to skip recommendation follow-through in next Sunday report |
| `/profile` | Display current health profile values (latest lab results + user profile) |
| `/profile update` | Conversationally update one or more `user_profile` fields |
| `/addfood <name>` | Add or update a food entry in the `indian_foods` nutrition table |
| `/help` | List available commands |

---

## Project Structure

```
nutrition-bot/
├── bot/
│   ├── main.py                        # Entry point, registers all handlers
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── meal.py                    # Photo handler + cachetools media group buffering
│   │   ├── health.py                  # PDF handler → HealthExtractorAgent or KnowledgeIngestorAgent
│   │   └── commands.py                # /profile, /help, "skip comparison"
│   └── agents/
│       ├── __init__.py
│       ├── base_agent.py              # BaseAgent — shared LangGraph wiring all agents inherit
│       ├── agent_loader.py            # Reads YAML configs → builds AGENT_REGISTRY at startup
│       ├── tool_registry.py           # All tools registered by name — agents reference in YAML
│       ├── orchestrator.py            # Router + general Q&A handler
│       ├── meal_analyzer.py           # Food/non-food check → macros + flags
│       ├── health_extractor.py        # PDF → lab values → confirm → save
│       ├── knowledge_ingestor.py      # PDF → extract findings → save JSON file
│       ├── pattern_detector.py        # 7-day streak detection + callouts
│       ├── daily_summary.py           # 11:30pm meal summary
│       ├── weekly_report.py           # Sunday report + recommendation comparison
│       ├── health_insights.py         # Conversational health Q&A (2-day lookback)
│       └── configs/                   # YAML config per agent — add new agent = new file here
│           ├── orchestrator.yaml
│           ├── meal_analyzer.yaml
│           ├── health_extractor.yaml
│           ├── knowledge_ingestor.yaml
│           ├── pattern_detector.yaml
│           ├── daily_summary.yaml
│           ├── weekly_report.yaml
│           └── health_insights.yaml
├── flows/
│   ├── __init__.py
│   ├── morning_report.py              # 10:30am — Fitbit + weather + nudges + quote
│   ├── alerts.py                      # 3pm lunch + 10:30pm dinner missed meal checks
│   ├── daily_summary.py               # 11:30pm — triggers DailySummaryAgent
│   ├── semantic_extraction.py         # Sunday 6pm — episodic → semantic memory extraction
│   └── weekly_report.py               # Sunday 8pm — triggers WeeklyReportAgent
├── knowledge_base/                    # One JSON file per ingested research article
├── db/
│   ├── __init__.py
│   ├── models.py                      # SQLAlchemy ORM models (SQLite dialect)
│   ├── queries.py                     # All shared query functions
│   └── migrations/
│       └── 001_initial_schema.sql     # Full schema — run once on VM SQLite
├── prompts/
│   ├── base_system.txt                # Health profile context injected into all agents
│   ├── morning_report.txt             # Single Claude call (Haiku) — no LangGraph agent
│   ├── meal_analyzer.txt
│   ├── health_extractor.txt
│   ├── pattern_detector.txt
│   ├── daily_summary.txt
│   ├── weekly_report.txt
│   └── health_insights.txt
├── tests/
│   ├── conftest.py                    # Shared fixtures: in-memory SQLite, tmp knowledge_base/ dir, mock Telegram, mock Claude
│   ├── unit/
│   │   ├── test_media_group_buffer.py # cachetools TTLCache buffering logic
│   │   ├── test_meal_handler.py       # Photo routing, meal type prompt
│   │   ├── test_health_handler.py     # PDF routing, confirmation flow
│   │   ├── test_commands.py           # /profile, skip comparison flag
│   │   ├── test_db_queries.py         # All query functions against test DB
│   │   └── test_pattern_logic.py      # Streak detection, dedup, escalation
│   ├── integration/
│   │   ├── test_meal_analyzer.py      # Agent: food check → analysis → DB save
│   │   ├── test_health_extractor.py   # Agent: PDF → extraction → confirmation
│   │   ├── test_pattern_detector.py   # Agent: injected data → callout content
│   │   ├── test_daily_summary.py      # Flow: aggregation → message format
│   │   ├── test_weekly_report.py      # Flow: recommendation comparison logic
│   │   ├── test_morning_report.py     # Flow: Fitbit + weather + nudge conditions
│   │   └── test_health_insights.py    # Agent: Q&A conversation, 2-day lookback
│   └── e2e/
│       ├── test_meal_logging_flow.py  # Photo → buffer → type select → analyze → save
│       ├── test_health_upload_flow.py # PDF → extract → confirm → save
│       └── test_alert_flow.py         # Missed meal conditions → alert fires/skips
├── .claude/
│   ├── CLAUDE.md                      # Project context for Claude (tech stack, conventions, agent map)
│   └── memory/
│       ├── MEMORY.md                  # Index of project memory files
│       └── decisions/
│           └── 001-tech-stack.md      # Why LangGraph, Prefect, Cloud SQL were chosen
├── config.py                          # Env vars, DB connection, zoneinfo setup
├── requirements.txt
└── requirements-dev.txt               # pytest, pytest-asyncio, freezegun, respx
```

---

## Implementation Plan

### Approach: Test-Driven Development

Every layer is built test-first: write a failing test that defines the expected behaviour, implement the minimum code to make it pass, verify. No implementation code is written without a failing test first.

**Test libraries:**
```
pytest
pytest-asyncio        # async handler + agent tests
freezegun             # freeze time for cron/alert condition tests
respx                 # mock Fitbit + Open-Meteo HTTP calls
```

SQLite tests use an in-memory database (`:memory:`) — no test DB setup needed. Knowledge base tests use a temporary `knowledge_base/` directory populated with fixture JSON files.

---

### Phase 1 — Infrastructure & Project Setup (no tests)

**Goal:** Working environment and Claude context before any code is written.

#### 1a. GCP Infrastructure

**Step 1 — Create the VM**

Run from your local machine with `gcloud` CLI authenticated:

```bash
# Create the VM
gcloud compute instances create nutrition-bot \
  --project=finance-assistant-476706 \
  --zone=us-central1-a \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-ssd \
  --tags=nutrition-bot
```

**Step 2 — Firewall rule for SSH via Cloud IAP**

```bash
gcloud compute firewall-rules create allow-iap-ssh-nutrition-bot \
  --project=finance-assistant-476706 \
  --allow=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=nutrition-bot \
  --description="IAP SSH access to nutrition-bot VM"
```

**Step 3 — Daily disk snapshot schedule**

```bash
# Create snapshot schedule (daily 2am, retain 30 days)
gcloud compute resource-policies create snapshot-schedule nutrition-bot-daily-backup \
  --project=finance-assistant-476706 \
  --region=us-central1 \
  --max-retention-days=30 \
  --on-source-disk-delete=keep-auto-snapshots \
  --daily-schedule \
  --start-time=02:00

# Attach to the boot disk
gcloud compute disks add-resource-policies nutrition-bot \
  --project=finance-assistant-476706 \
  --zone=us-central1-a \
  --resource-policies=nutrition-bot-daily-backup
```

**Step 4 — SSH into the VM**

```bash
gcloud compute ssh nutrition-bot \
  --project=finance-assistant-476706 \
  --zone=us-central1-a \
  --tunnel-through-iap
```

**Step 5 — Bootstrap the VM** (run inside the VM)

```bash
# System update
sudo apt-get update && sudo apt-get upgrade -y

# Python 3.11 + git
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip git sqlite3

# App directories
sudo mkdir -p /opt/nutrition-bot
sudo chown $USER:$USER /opt/nutrition-bot
mkdir -p /opt/nutrition-bot/knowledge_base
mkdir -p /opt/nutrition-bot/.cache
mkdir -p /opt/nutrition-bot/logs
mkdir -p /opt/nutrition-bot/logs/traces

# Python venv
python3.11 -m venv /opt/nutrition-bot/venv
echo "source /opt/nutrition-bot/venv/bin/activate" >> ~/.bashrc
source /opt/nutrition-bot/venv/bin/activate
```

**Step 6 — Create `.env`** (fill in real values)

```bash
cat > /opt/nutrition-bot/.env << 'EOF'
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=7659563001
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL_HEAVY=claude-opus-4-8
ANTHROPIC_MODEL_MID=claude-sonnet-4-6
ANTHROPIC_MODEL_FAST=claude-haiku-4-5-20251001
FITBIT_CLIENT_ID=23VDST
FITBIT_CLIENT_SECRET=
FITBIT_REFRESH_TOKEN=
SQLITE_DB_PATH=/opt/nutrition-bot/app.db
KNOWLEDGE_BASE_PATH=/opt/nutrition-bot/knowledge_base
DISKCACHE_PATH=/opt/nutrition-bot/.cache
EOF
chmod 600 /opt/nutrition-bot/.env
```

**Step 7 — Initialise SQLite DB**

```bash
sqlite3 /opt/nutrition-bot/app.db < /opt/nutrition-bot/db/migrations/001_initial_schema.sql

# Verify
sqlite3 /opt/nutrition-bot/app.db ".tables"
# Expected: daily_health_logs  indian_foods  meal_logs  patterns
#           user_health_profile  user_nutrition_guidance  user_profile
#           user_semantic_memory  daily_summaries  weekly_reports
```

- [ ] VM created and SSH accessible
- [ ] Firewall rule applied
- [ ] Snapshot schedule attached to disk
- [ ] Python 3.11 installed, venv active
- [ ] `/opt/nutrition-bot/` directory structure in place
- [ ] `.env` populated with all secrets
- [ ] SQLite DB initialised — all 10 tables present

#### 1b. Claude Project Context

Create `.claude/CLAUDE.md` at the project root. This gives Claude full context when working in this repo so it never needs to be re-explained:

```markdown
# nutrition-bot

## What This Is
Standalone Telegram bot — personal dietary nutritionist targeting lower A1C
and cholesterol. Single user. See full spec at:
`docs/superpowers/specs/2026-05-25-nutrition-tracker-design.md`

## Tech Stack
Python 3.11+, python-telegram-bot v20+, LangGraph v0.4+,
Claude Opus 4.8 (heavy) / Sonnet 4.6 (mid) / Haiku 4.5 (fast),
SQLite (WAL mode), knowledge_base/ JSON files (structured extraction),
Prefect v3+, Fitbit API, Open-Meteo

## Key Conventions
- All times in America/Los_Angeles via zoneinfo — never hardcode UTC offsets
- Never read source files if a CodeLedger node exists — use the node
- Tests are mandatory before implementation — see Implementation Plan in spec
- No image storage — photos are analyzed on receipt and discarded
- Single user — no user_id scoping needed in DB queries

## Agent Files
bot/agents/ — one file per agent, all use LangGraph StateGraph
bot/handlers/ — Telegram update routing only, no business logic
flows/ — Prefect @flow functions, one file per scheduled job
db/queries.py — all DB access goes through here, never raw SQL in agents

## Environment
- Local dev: use SQLite :memory: + tmp knowledge_base/ dir (see tests/conftest.py)
- Secrets in .env — never commit
```

Create `.claude/memory/MEMORY.md` — project memory index for Claude to track decisions and context that evolve during development:

```markdown
# nutrition-bot Memory

## Architecture Decisions
- [Initial tech stack](decisions/001-tech-stack.md)

## Open Questions
- None yet
```

Also create `.claude/memory/decisions/001-tech-stack.md`:

```markdown
---
name: Initial Tech Stack
description: Core technology decisions made during design phase
type: project
---

LangGraph chosen over CrewAI (no crash recovery) and raw Anthropic SDK
(too much boilerplate for 6 agents). Prefect chosen over system crontab
for retry logic and observability. SQLite chosen over Cloud SQL — single user,
zero cost, WAL mode handles two-process (bot + Prefect) safely.
Three-tier model split — all Anthropic, single SDK: Opus 4.8 for complex reasoning
(WeeklyReport, HealthInsights), Sonnet 4.6 for mid-complexity (MealAnalyzer,
HealthExtractor, KnowledgeIngestor), Haiku 4.5 for fast tasks (Orchestrator,
PatternDetector, DailySummary, flows). Model IDs in .env for easy upgrades.
Knowledge base uses structured extraction (JSON files) instead of FAISS + Vertex AI
embeddings — corpus is 10-20 curated documents (~6,000 tokens total), so full
context injection on every call is cheaper and more reliable than retrieval.
No image storage — analyze on receipt, discard. Indian food nutrition data
in structured SQLite table (not vector store) — SQL lookup is faster and
more accurate than semantic search for tabular nutrition data.
```

---

### Phase 2 — DB Layer

**Goal:** All query functions tested against an in-memory SQLite database.

**Write tests first (`tests/unit/test_db_queries.py`):**
- Insert meal log → query by date → assert returned correctly
- Insert multiple snacks same day → query all → assert both returned
- Insert two health profile rows (different report_date) → query latest → assert most recent returned
- Insert three health profile rows → query history → assert all three returned in date order
- Insert user_profile row → query → assert all fields returned
- Insert nutrition guidance rows → delete all → insert fresh → assert only new rows present
- Query last 7 days with missing days → assert gaps handled (no crash)
- Query last 2 days → assert only 2 days returned regardless of older data

**Then implement:**
- `db/models.py` — SQLAlchemy models for all 10 tables (`daily_health_logs`, `meal_logs`, `user_profile`, `user_health_profile`, `user_nutrition_guidance`, `daily_summaries`, `weekly_reports`, `patterns`, `indian_foods`, `user_semantic_memory`)
- `db/queries.py` — typed query functions used by all agents and flows

**Verify:** `pytest tests/unit/test_db_queries.py` — all pass

---

### Phase 3 — Bot Handlers

**Goal:** Telegram update routing works correctly before agents are wired in.

**Write tests first:**

`tests/unit/test_media_group_buffer.py`:
- Two photos with same `media_group_id` arrive within 2s → buffered as one group
- Two photos with different `media_group_id` → treated as separate meals
- Single photo (no `media_group_id`) → processed immediately

`tests/unit/test_meal_handler.py`:
- Photo received → meal type inline keyboard sent once (not per photo)
- Non-food photo → classification prompt sent
- Meal type selected → acknowledgment sent, analysis queued

`tests/unit/test_health_handler.py`:
- PDF document received → routed to HealthExtractorAgent
- Non-PDF document → ignored with helpful message

`tests/unit/test_commands.py`:
- `/profile` with no health data → "No profile uploaded yet"
- `/profile` with data → formatted health values returned
- `"skip comparison"` → `weekly_reports.skip_comparison` flagged in DB

**Then implement:** `bot/handlers/meal.py`, `health.py`, `commands.py`

**Verify:** `pytest tests/unit/test_*handler* tests/unit/test_media*` — all pass

---

### Phase 4 — Agents (largest phase)

**Goal:** Each agent produces correct output given known inputs. Claude calls are mocked in unit tests; real calls used in integration tests.

**Build order — each agent follows the same pattern: test → implement → verify:**

#### 4a. MealAnalyzerAgent
`tests/integration/test_meal_analyzer.py`:
- Food photo → `foods_identified` contains expected items
- Beverage in photo → identified and macros estimated
- Non-food photo → `is_food: false` returned, no analysis
- High-GI meal → `glycemic_load: high` + `a1c_flags` populated
- Analysis saved to `meal_logs` table

#### 4b. HealthExtractorAgent
`tests/integration/test_health_extractor.py`:
- PDF with A1C 6.2%, LDL 142 → extracted values match
- Confirmation message contains all extracted fields
- Confirmed → new row inserted into `user_health_profile` with today's `report_date`
- Second upload same date → `UNIQUE` constraint on `report_date` → row updated (not duplicated)
- Confirmed → `HealthExtractorAgent` runs 3-step update: deactivate stale rules (with remark), reactivate relevant prior rules, insert new rules — no rows ever deleted
- Two lab uploads → `user_health_profile` has 2 rows; guidance reflects latest values only

#### 4c. PatternDetectorAgent
`tests/unit/test_pattern_logic.py` + `tests/integration/test_pattern_detector.py`:
- 3 consecutive high-GI days → callout fires on day 3
- Day 4 of same pattern → escalated message ("4 days in a row")
- diskcache key set → same callout not sent twice same day
- Pattern breaks → streak resets, callout stops
- < 3 days data → no callout

#### 4d. DailySummaryAgent
`tests/integration/test_daily_summary.py`:
- Day with 3 meals logged → summary includes all meals + total macros
- Day with 0 meals logged → summary notes no meals logged
- A1C flag present → flagged foods + alternatives in message
- Dietary score computed and included

#### 4e. WeeklyReportAgent
`tests/integration/test_weekly_report.py`:
- Week 1 (no prior recommendations) → comparison section absent
- `skip_comparison = TRUE` → comparison section absent
- Last week recommended "reduce white rice" + this week has white rice → "not followed"
- Last week recommended "reduce white rice" + this week has no white rice → "followed"

#### 4f. HealthInsightsAgent
`tests/integration/test_health_insights.py`:
- "why am I bloated?" → follow-up question sent (not an immediate answer)
- Follow-up answered → 2-day meal data queried + explanation returned
- High-FODMAP foods in last 2 days → identified in explanation
- No meals logged in last 2 days → gracefully noted in response

**Verify after each:** `pytest tests/integration/test_<agent>.py` — all pass

---

### Phase 5 — Prefect Flows

**Goal:** All scheduled flows produce correct output and retry on transient failures.

**Write tests first:**

`tests/integration/test_morning_report.py` (with `freezegun` + `respx`):
- Yesterday steps = 3,000 → nudge included in message
- Yesterday steps = 8,000 → nudge absent
- Last night sleep = 5.5hrs → sleep nudge included
- Last night sleep = 7.5hrs → sleep nudge absent
- Rain in forecast → time window included
- No rain → rain line absent
- Fitbit API returns 429 → flow retries, succeeds on retry 2

`tests/integration/test_daily_summary.py`:
- Flow runs at 11:30pm → DailySummaryAgent called with today's meals
- Claude API timeout → flow retries up to 3 times

`tests/integration/test_morning_report.py` + `test_alert_flow.py`:
- 3pm check: lunch logged → no alert sent
- 3pm check: no lunch, no breakfast → alert sent
- 10:30pm check: dinner logged → no alert sent
- 10:30pm check: no dinner → alert sent

**Then implement:** `flows/morning_report.py`, `alerts.py`, `daily_summary.py`, `semantic_extraction.py`, `weekly_report.py`

**Verify:** `pytest tests/integration/test_*flow* tests/integration/test_morning* tests/integration/test_alert*` — all pass

---

### Phase 6 — End-to-End Tests

**Goal:** Full user journeys work from Telegram update to DB state + outbound message.

`tests/e2e/test_meal_logging_flow.py`:
1. Simulate Telegram album (3 photos, same `media_group_id`)
2. Assert single meal-type keyboard sent
3. Simulate user tapping [Lunch]
4. Assert acknowledgment sent + `meal_logs` row created
5. Assert analysis saved to DB

`tests/e2e/test_health_upload_flow.py`:
1. Simulate PDF document message
2. Assert confirmation message sent with extracted values
3. Simulate [Confirm] tap
4. Assert `user_health_profile` table updated

`tests/e2e/test_alert_flow.py`:
1. Freeze time to 3:00pm PST with no meals logged
2. Run `lunch_alert_flow`
3. Assert Telegram alert message sent
4. Log a lunch meal
5. Run again → assert no alert sent

**Verify:** `pytest tests/e2e/` — all pass

---

### Phase 7 — Deployment

- [ ] Verify Monocle traces writing to `/opt/nutrition-bot/logs/traces/` — tail the directory after sending a test message
  ```bash
  # Download traces to Mac for inspection
  gcloud compute scp "nutrition-bot:/opt/nutrition-bot/logs/traces/*.json" ~/Downloads/ \
    --project=finance-assistant-476706 --zone=us-central1-a --tunnel-through-iap
  ```
- [ ] Create `systemd` service for bot process (`nutrition-bot.service`)
- [ ] Create `systemd` service for Prefect server (`prefect-server.service`)
- [ ] Deploy Prefect flow schedules: `prefect deploy`
- [ ] Install and start Uptime Kuma via Docker on the VM:
  ```bash
  docker run -d --restart=always \
    -p 3001:3001 \
    -v uptime-kuma:/app/data \
    --name uptime-kuma \
    louislam/uptime-kuma:1
  ```
- [ ] Add push monitor in Uptime Kuma → copy the push URL
- [ ] Add heartbeat to bot: every 5 min, bot pings the Uptime Kuma push URL
  ```python
  # In bot startup, schedule a recurring job:
  async def heartbeat(context):
      async with aiohttp.ClientSession() as s:
          await s.get(UPTIME_KUMA_PUSH_URL)
  application.job_queue.run_repeating(heartbeat, interval=300)
  ```
- [ ] Configure Uptime Kuma notification → Telegram (send alert to `TELEGRAM_CHAT_ID` if no ping for 10 min)
- [ ] Smoke test: send a food photo via Telegram → confirm end-to-end
- [ ] Smoke test: manually trigger `morning_report_flow` → confirm message received
- [ ] Upload a lab report PDF → confirm health profile saved
- [ ] Monitor Prefect dashboard for first 48hrs

---

### Build Order Summary

```
Phase 1a: GCP infra             → VM + SQLite setup + disk snapshot + .env + knowledge_base/ dir
Phase 1b: Claude project setup  → .claude/CLAUDE.md + memory/MEMORY.md
Phase 2:  DB layer              → unit tests → models + queries
Phase 3:  Bot handlers          → unit tests → handlers
Phase 4:  Agents (6 agents)     → integration tests → agent implementations
Phase 5:  Prefect flows         → integration tests → flow implementations
Phase 6:  E2E tests             → full journey validation
Phase 7:  Deploy                → systemd + Prefect deploy + smoke tests
```

Each phase must have all tests passing before the next phase begins.
