# tests/integration/test_meal_analyzer.py

## Summary
Integration tests for MealAnalyzerAgent. Written TDD-first. Uses mock_anthropic (no real API calls). Covers: instantiation, model/tool assertions, invocation without crash (stub LLM), DB side-effects via direct tool calls (save_meal_analysis), beverage presence in foods_identified, graceful handling of missing health profile, and required output field verification.

## Functions
- _photo_state(message, photos) — helper; builds a minimal AgentState dict for photo input
- _insert_health_profile(session) — helper; inserts UserHealthProfile row directly via ORM

## Non-function code
- TestMealAnalyzerInstantiation — 4 tests: instantiates, is BaseAgent, correct model, has expected tools
- TestMealAnalyzerInvocation — 5 tests: saves_meal_to_db, non_food_sends_clarification, includes_beverages_in_analysis, handles_missing_health_profile, json_output_has_required_fields
- TestMealAnalyzerContextInjection — 2 tests: system_prompt_includes_health_profile, system_prompt_includes_meal_analyzer_instructions

## Imports
- pytest
- langchain_core.messages.HumanMessage

## Imported by
- pytest (auto-discovered)

## Tags
tests, integration, meal-analyzer, photo, tdd

## Node path
tests/integration/test_meal_analyzer.py
