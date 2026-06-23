# bot/agents/orchestrator.py

## Summary
Thin wrapper that instantiates OrchestratorAgent by loading the YAML config from bot/agents/configs/orchestrator.yaml via load_agent, then delegates all state and graph construction to BaseAgent. Handles all real-time Telegram message routing (text, command, pdf triggers) using Claude Haiku.

## Functions
- OrchestratorAgent.__init__() — calls load_agent with orchestrator.yaml, passes resolved model/tokens/prompt/tools to BaseAgent.__init__

## Non-function code
N/A

## Imports
- pathlib.Path
- bot.agents.base_agent.BaseAgent
- bot.agents.agent_loader.load_agent

## Imported by
- tests/integration/test_orchestrator.py — tested here
- bot/handlers/ (planned) — instantiated for routing

## Tags
agents, orchestrator, langgraph, haiku, routing

## Node path
bot/agents/orchestrator.py
