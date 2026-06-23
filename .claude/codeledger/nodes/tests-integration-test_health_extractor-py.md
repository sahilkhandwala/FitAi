# tests/integration/test_health_extractor.py

## Summary
Integration tests for HealthExtractorAgent. Written TDD-first. Uses mock_anthropic (no real API calls). Covers: instantiation, model/tool assertions, no-context-injection verification, invocation without crash (stub LLM), missing fields handled gracefully (None hdl/triglycerides), duplicate report date returns 'duplicate_date' not exception, and generate_nutrition_guidance called after confirm.

## Functions
- _pdf_state(message) — helper; builds a minimal AgentState dict for PDF input
- _insert_health_profile_for_date(session, report_date) — helper; inserts UserHealthProfile row for specific date

## Non-function code
- TestHealthExtractorInstantiation — 5 tests: instantiates, is BaseAgent, correct model, has expected tools, no_context_injection
- TestHealthExtractorInvocation — 4 tests: presents_values_for_confirmation, handles_missing_fields, duplicate_report_date_friendly_error, generates_guidance_on_confirm
- TestHealthExtractorSystemPrompt — 1 test: system_prompt_contains_instructions

## Imports
- pytest
- langchain_core.messages.HumanMessage

## Imported by
- pytest (auto-discovered)

## Tags
tests, integration, health-extractor, pdf, lab-report, tdd

## Node path
tests/integration/test_health_extractor.py
