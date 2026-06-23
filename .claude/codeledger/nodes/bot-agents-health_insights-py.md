# bot/agents/health_insights.py

## Summary
HealthInsightsAgent — a thin BaseAgent subclass wired to the health_insights.yaml config. Loads the agent via load_agent() at init time, which resolves the Opus model, injects all 5 context blocks into the system prompt, and resolves the 5 tools (query_last_2_days_meals, query_last_2_days_steps, query_last_2_days_sleep, ask_web_search_permission, send_telegram_msg). Unique among all agents: use_checkpointer=True (driven by checkpointer: true in YAML) for multi-turn conversational Q&A.

## Functions
- HealthInsightsAgent.__init__() — calls load_agent with the absolute config path, passes all resolved fields including use_checkpointer=True to BaseAgent.__init__

## Non-function code
- `_CONFIG` — absolute Path to bot/agents/configs/health_insights.yaml

## Imports
- pathlib.Path
- bot.agents.base_agent.BaseAgent
- bot.agents.agent_loader.load_agent

## Imported by
- bot/handlers/commands.py (planned) — routes health_question trigger to this agent
- bot/agents/agent_loader.py — does NOT import this; HealthInsightsAgent is instantiated by AGENT_REGISTRY build

## Tags
agents, health-insights, opus, langgraph, checkpointer, multi-turn

## Node path
bot/agents/health_insights.py
