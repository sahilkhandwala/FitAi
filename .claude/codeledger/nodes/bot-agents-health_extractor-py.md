# bot/agents/health_extractor.py

## Summary
Thin LangGraph agent wrapper for lab report PDF extraction. Loads config from health_extractor.yaml (Sonnet model, tools: confirm_with_user, save_health_profile, generate_nutrition_guidance, no context injection) and delegates all logic to prompts/health_extractor.txt and tool_registry.py. No context injection — reads raw PDF without Sahil's existing profile.

## Functions
- HealthExtractorAgent.__init__() — loads _CONFIG via load_agent(), delegates to BaseAgent

## Non-function code
- `_CONFIG` — Path(__file__).parent / "configs" / "health_extractor.yaml"

## Imports
- pathlib.Path
- bot.agents.agent_loader.load_agent
- bot.agents.base_agent.BaseAgent

## Imported by
- tests/integration/test_health_extractor.py — instantiates and tests
- bot/handlers/health.py (planned) — routes lab report PDFs to this agent

## Tags
agents, health, pdf, lab-report, langgraph, sonnet

## Node path
bot/agents/health_extractor.py
