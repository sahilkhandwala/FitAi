# tests/integration/test_knowledge_ingestor.py

## Summary
TDD integration tests for KnowledgeIngestorAgent. Written before implementation. Tests cover: instantiation without error (with FakeChatAnthropic confirmed wired), returning messages list on invoke with a PDF state, and two direct-tool tests for save_to_knowledge_base: verifying the file is written and verifying the JSON schema has the correct keys (source, ingested_at, relevance_tags, findings) with filename excluded from the JSON body.

## Functions
- patch_base_agent_llm(monkeypatch, mock_anthropic) — autouse fixture; patches bot.agents.base_agent.ChatAnthropic
- _make_pdf_state(text) — helper; constructs AgentState with research_article input_type
- TestKnowledgeIngestorInstantiates.test_knowledge_ingestor_instantiates() — verifies no error on init, graph built, fake LLM wired
- TestKnowledgeIngestorInvoke.test_knowledge_ingestor_returns_messages(session, mock_anthropic) — verifies result["messages"] is non-empty list
- TestSaveToKnowledgeBaseTool.test_save_to_knowledge_base_tool_writes_file(tmp_path, monkeypatch, session) — patches KNOWLEDGE_BASE_DIR, verifies file written and result == "saved"
- TestSaveToKnowledgeBaseTool.test_knowledge_base_json_schema_correct(tmp_path, monkeypatch, session) — verifies JSON keys/types and that filename is NOT in JSON body

## Non-function code
N/A

## Imports
- json, pytest
- langchain_core.messages.HumanMessage
- bot.agents.base_agent.AgentState
- bot.agents.knowledge_ingestor.KnowledgeIngestorAgent (imported inside tests)
- bot.agents.tool_registry (init_tools, save_to_knowledge_base imported inside tests)

## Imported by
N/A (test file)

## Tags
tests, integration, knowledge-ingestor, tdd

## Node path
tests/integration/test_knowledge_ingestor.py
