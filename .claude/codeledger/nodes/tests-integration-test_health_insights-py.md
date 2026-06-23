# tests/integration/test_health_insights.py

## Summary
Integration tests for HealthInsightsAgent. TDD: written before implementation. Tests cover instantiation (does not raise, is BaseAgent, correct model, use_checkpointer=True), invocation (returns messages, handles no meal data, handles various symptom questions), context injection (all 5 context blocks with session+KB, KB content, agent instructions), and tools (correct tool set from YAML). Uses mock_anthropic to avoid real API calls.

## Functions
- _make_state(message) — helper; builds minimal AgentState dict for testing
- _insert_health_profile(session) — helper; inserts UserHealthProfile row via ORM
- _insert_semantic_memory(session) — helper; inserts UserSemanticMemory row via ORM

## Non-function code
- TestHealthInsightsInstantiation — 4 tests: instantiates, is_base_agent, correct_model, has_checkpointer_flag
- TestHealthInsightsInvocation — 3 tests: returns_messages (passes thread_id="test-thread-1"), handles_no_meal_data (passes thread_id), handles_general_health_question (passes unique thread_ids)
- TestHealthInsightsContextInjection — 3 tests: injects_full_context, injects_kb_content, system_prompt_contains_instructions
- TestHealthInsightsTools — 1 test: has_expected_tools

## Imports
- pytest
- langchain_core.messages.HumanMessage

## Imported by
- pytest — auto-discovered

## Tags
tests, integration, health-insights, checkpointer, tdd

## Node path
tests/integration/test_health_insights.py
