# tests/integration/test_orchestrator.py

## Summary
TDD integration tests for OrchestratorAgent. Written before implementation. Tests cover: instantiation without error (with graph built and FakeChatAnthropic confirmed wired), returning messages list on invoke, handling a general nutrition question, and gracefully handling an empty health profile DB. Uses autouse fixture to patch ChatAnthropic in bot.agents.base_agent's namespace (not just langchain_anthropic) to avoid the import-time reference capture problem.

## Functions
- patch_base_agent_llm(monkeypatch, mock_anthropic) — autouse fixture; patches bot.agents.base_agent.ChatAnthropic so BaseAgent uses FakeChatAnthropic
- _make_state(text) — helper; constructs a minimal AgentState with text input_type
- TestOrchestratorInstantiates.test_orchestrator_instantiates() — verifies no error on init, graph built, fake LLM wired
- TestOrchestratorInvoke.test_orchestrator_returns_messages(session, mock_anthropic) — verifies result["messages"] is a non-empty list
- TestOrchestratorInvoke.test_orchestrator_handles_general_question(session, mock_anthropic) — verifies invoke on nutrition question succeeds
- TestOrchestratorInvoke.test_orchestrator_handles_empty_health_profile(session, mock_anthropic) — verifies no crash when no health profile rows in DB

## Non-function code
N/A

## Imports
- pytest, json
- langchain_core.messages.HumanMessage
- bot.agents.base_agent.AgentState
- bot.agents.orchestrator.OrchestratorAgent (imported inside tests)
- bot.agents.tool_registry.init_tools (imported inside tests)

## Imported by
N/A (test file)

## Tags
tests, integration, orchestrator, tdd

## Node path
tests/integration/test_orchestrator.py
