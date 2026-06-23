# bot/agents/weekly_report.py

## Summary
WeeklyReportAgent — a thin BaseAgent subclass wired to the weekly_report.yaml config. Loads the agent via load_agent() at init time, which resolves the Opus model, injects all 5 context blocks (health_profile, user_profile, nutrition_guidance, semantic_memory, knowledge_base) into the system prompt, and resolves the 3 tools (query_week_meals, get_last_week_recommendations, send_telegram_msg). Does not use a checkpointer.

## Functions
- WeeklyReportAgent.__init__() — calls load_agent with the absolute config path, passes all resolved fields to BaseAgent.__init__

## Non-function code
- `_CONFIG` — absolute Path to bot/agents/configs/weekly_report.yaml

## Imports
- pathlib.Path
- bot.agents.base_agent.BaseAgent
- bot.agents.agent_loader.load_agent

## Imported by
- flows/weekly_report_flow.py (planned) — instantiates WeeklyReportAgent for Sunday 8pm job
- bot/agents/agent_loader.py — does NOT import this; WeeklyReportAgent is only used by flows

## Tags
agents, weekly-report, opus, langgraph

## Node path
bot/agents/weekly_report.py
