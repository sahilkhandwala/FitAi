# tests/unit/test_tool_registry.py

## Summary
TDD unit tests for bot/agents/tool_registry.py. Written before implementation. Tests cover: get_health_profile (empty and with data), get_nutrition_guidance filtering inactive rules, query_knowledge_base loading JSON files, save_to_knowledge_base writing files, and save_meal_analysis inserting DB rows. All tool calls use .invoke({...}) since @tool objects are not plain callables.

## Functions
- _insert_health_profile(session, report_date, a1c, ldl, hdl) — helper to insert UserHealthProfile row
- _insert_guidance(session, rule, category, is_active) — helper to insert UserNutritionGuidance row
- TestGetHealthProfile.test_returns_none_when_empty(session) — verifies None when no profile exists
- TestGetHealthProfile.test_returns_dict_when_data_exists(session) — verifies dict with a1c/ldl/hdl keys
- TestGetNutritionGuidance.test_filters_inactive_rules(session) — verifies only active rules returned
- TestQueryKnowledgeBase.test_loads_json_files(knowledge_base_dir, monkeypatch) — patches KNOWLEDGE_BASE_DIR, verifies both JSON files loaded
- TestSaveToKnowledgeBase.test_writes_file(tmp_path, monkeypatch) — patches KNOWLEDGE_BASE_DIR to tmp_path, verifies JSON file written with correct content
- TestSaveMealAnalysis.test_inserts_row(session) — calls save_meal_analysis.invoke, verifies row in DB via get_todays_meals

## Non-function code
- `LA` — ZoneInfo("America/Los_Angeles") for test helpers

## Imports
- json, pytest, datetime, zoneinfo.ZoneInfo
- bot.agents.tool_registry (init_tools, individual tools)
- db.models (UserHealthProfile, UserNutritionGuidance) for test helpers
- db.queries.get_todays_meals for verification

## Imported by
N/A (test file)

## Tags
tests, unit, tool-registry, tdd

## Node path
tests/unit/test_tool_registry.py
