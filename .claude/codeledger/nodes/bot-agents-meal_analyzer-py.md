# bot/agents/meal_analyzer.py

## Summary
Thin LangGraph agent wrapper for meal photo analysis. Loads config from meal_analyzer.yaml (Sonnet model, tools: save_meal_analysis, ask_web_search_permission, get_indian_food, context: health_profile + user_profile + nutrition_guidance + semantic_memory + knowledge_base) and delegates all logic to prompts/meal_analyzer.txt and tool_registry.py.

## Functions
- MealAnalyzerAgent.__init__() — loads _CONFIG via load_agent(), delegates to BaseAgent

## Non-function code
- `_CONFIG` — Path(__file__).parent / "configs" / "meal_analyzer.yaml"

## Imports
- pathlib.Path
- bot.agents.agent_loader.load_agent
- bot.agents.base_agent.BaseAgent

## Imported by
- tests/integration/test_meal_analyzer.py — instantiates and tests
- bot/handlers/meal.py (planned) — routes photo updates to this agent

## Tags
agents, meal, photo, langgraph, sonnet

## Node path
bot/agents/meal_analyzer.py
