# bot/agents/daily_summary.py

## Summary
DailySummaryAgent — thin BaseAgent subclass that loads daily_summary.yaml at instantiation. Injects 3 context blocks (health_profile, user_profile, nutrition_guidance) into the system prompt. Uses tools query_todays_meals and send_telegram_msg. Triggered by the 11:30pm Prefect daily_summary_flow.

## Functions
- DailySummaryAgent.__init__() — calls load_agent(daily_summary.yaml), passes resolved model/tokens/prompt/tools to super().__init__()

## Non-function code
None.

## Imports
- pathlib.Path
- bot.agents.base_agent.BaseAgent
- bot.agents.agent_loader.load_agent

## Imported by
- flows/daily_summary_flow.py (planned) — instantiates DailySummaryAgent at flow run time
- tests/integration/test_daily_summary.py — imports DailySummaryAgent for testing

## Tags
agents, langgraph, haiku, daily-summary, context-injection

## Node path
bot/agents/daily_summary.py
