# tests/integration/test_weekly_report.py

## Summary
Integration tests for WeeklyReportAgent. TDD: written before implementation. Tests cover instantiation (does not raise, is BaseAgent, correct model, no checkpointer), invocation (returns messages, handles empty DB for Week 1, handles prior report), and context injection (KB content in system_prompt, all 5 context blocks present, agent instructions present). Uses mock_anthropic to avoid real API calls.

## Functions
- _make_state(input_type, message) — helper; builds minimal AgentState dict for testing
- _insert_weekly_report(session, week_start, score_delta) — helper; inserts WeeklyReport row via ORM

## Non-function code
- TestWeeklyReportInstantiation — 4 tests: instantiates, is_base_agent, correct_model, no_checkpointer
- TestWeeklyReportInvocation — 3 tests: returns_messages, handles_no_prior_report, with_prior_report
- TestWeeklyReportContextInjection — 3 tests: injects_knowledge_base, injects_all_five_context_blocks, system_prompt_contains_agent_instructions

## Imports
- pytest
- langchain_core.messages.HumanMessage

## Imported by
- pytest — auto-discovered

## Tags
tests, integration, weekly-report, tdd

## Node path
tests/integration/test_weekly_report.py
