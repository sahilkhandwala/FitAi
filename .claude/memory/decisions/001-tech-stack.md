---
name: Initial Tech Stack
description: Core technology decisions made during design phase
metadata:
  type: project
---

LangGraph chosen over CrewAI (no crash recovery) and raw Anthropic SDK
(too much boilerplate for 8 agents). Prefect chosen over system crontab
for retry logic and observability. SQLite chosen over Cloud SQL — single user,
zero cost, WAL mode handles two-process (bot + Prefect) safely.

Three-tier model split — all Anthropic, single SDK:
- Opus 4.8: WeeklyReportAgent, HealthInsightsAgent (complex reasoning)
- Sonnet 4.6: MealAnalyzerAgent, HealthExtractorAgent, KnowledgeIngestorAgent (mid-complexity)
- Haiku 4.5: OrchestratorAgent, PatternDetectorAgent, DailySummaryAgent, flows (fast/cheap)
Model IDs in .env for easy upgrades without code changes.

Knowledge base uses structured extraction (JSON files) instead of FAISS + embeddings.
Corpus is 10-20 curated documents (~6,000 tokens total) — full context injection
on every call is cheaper and more reliable than retrieval for this size.

Context injection vs tool-call split: 4 agents (MealAnalyzer, DailySummary,
WeeklyReport, HealthInsights) inject context unconditionally — always consume it.
OrchestratorAgent uses tool-calls — only needs context when answering directly,
not when routing. HealthExtractor, KnowledgeIngestor, PatternDetector need no
profile context at all.

No image storage — analyze on receipt, discard. Indian food nutrition data
in structured SQLite table — SQL lookup is faster and more accurate than
semantic search for tabular nutrition data.

user_health_profile accumulates one row per lab report (not single-row upsert)
so A1C/LDL trend analysis is possible over time. user_nutrition_guidance is
full-replacement on each lab confirm — derived guidance, not raw data.

**Why:** Single user, ~$12/month infra target, zero ops overhead.
**How to apply:** Don't suggest Redis, Cloud SQL, vector stores, or multi-SDK
approaches — all have been evaluated and rejected for this use case.
