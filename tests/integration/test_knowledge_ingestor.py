"""
Integration tests for KnowledgeIngestorAgent.

TDD: written before bot/agents/knowledge_ingestor.py exists.
Expected red phase: ImportError on 'from bot.agents.knowledge_ingestor import KnowledgeIngestorAgent'.
"""

import json
import pytest
from langchain_core.messages import HumanMessage

from bot.agents.base_agent import AgentState


# ---------------------------------------------------------------------------
# Fixture: patch ChatAnthropic in the module where BaseAgent imports it
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_base_agent_llm(monkeypatch, mock_anthropic):
    """
    Patch ChatAnthropic in bot.agents.base_agent's namespace.
    mock_anthropic (from conftest) already patches langchain_anthropic.ChatAnthropic,
    but base_agent captures the reference at import time via
    'from langchain_anthropic import ChatAnthropic'.
    We must also patch the already-bound name.
    """
    monkeypatch.setattr("bot.agents.base_agent.ChatAnthropic", mock_anthropic)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf_state(text: str = "Please ingest this research article.") -> AgentState:
    return AgentState(
        input_type="research_article",
        telegram_chat_id=123456789,
        messages=[HumanMessage(content=text)],
        media_group_id=None,
        photos=[],
        analysis_result=None,
        next_agent=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestKnowledgeIngestorInstantiates:
    def test_knowledge_ingestor_instantiates(self):
        """KnowledgeIngestorAgent() does not raise and its graph is built."""
        from bot.agents.knowledge_ingestor import KnowledgeIngestorAgent

        agent = KnowledgeIngestorAgent()

        assert agent is not None
        assert agent.graph is not None
        # Confirm the fake LLM is wired — not the real Anthropic client
        assert type(agent._llm).__name__ == "FakeChatAnthropic"


class TestKnowledgeIngestorInvoke:
    def test_knowledge_ingestor_returns_messages(self, session, mock_anthropic):
        """Invoking with a PDF state returns a result dict with a messages list."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.knowledge_ingestor import KnowledgeIngestorAgent

        init_tools(session)
        agent = KnowledgeIngestorAgent()

        result = agent.invoke(_make_pdf_state())

        assert "messages" in result
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) >= 1


class TestSaveToKnowledgeBaseTool:
    def test_save_to_knowledge_base_tool_writes_file(self, tmp_path, monkeypatch, session):
        """
        Directly call save_to_knowledge_base tool — verify JSON file written.
        Does not go through the agent; tests the tool side effect directly.
        """
        import bot.agents.tool_registry as tr
        from bot.agents.tool_registry import save_to_knowledge_base

        monkeypatch.setattr(tr, "KNOWLEDGE_BASE_DIR", tmp_path)

        result = save_to_knowledge_base.invoke({
            "filename": "test_fiber_study",
            "source": "Fiber and A1C — Doe et al. 2026",
            "ingested_at": "2026-06-22",
            "relevance_tags": ["a1c", "fiber"],
            "findings": [
                "High fiber intake reduces A1C by 0.5% over 12 weeks.",
                "Soluble fiber from legumes most effective.",
            ],
        })

        assert result == "saved"
        output_file = tmp_path / "test_fiber_study.json"
        assert output_file.exists()

    def test_knowledge_base_json_schema_correct(self, tmp_path, monkeypatch, session):
        """
        Verify the written JSON has required top-level keys:
        source, ingested_at, relevance_tags (list), findings (list).
        filename is used only for the file path — it does NOT appear in the JSON.
        """
        import bot.agents.tool_registry as tr
        from bot.agents.tool_registry import save_to_knowledge_base

        monkeypatch.setattr(tr, "KNOWLEDGE_BASE_DIR", tmp_path)

        save_to_knowledge_base.invoke({
            "filename": "schema_test",
            "source": "Omega-3 and HDL — Smith et al. 2026",
            "ingested_at": "2026-06-22",
            "relevance_tags": ["hdl", "ldl"],
            "findings": ["EPA+DHA raises HDL by 4-8% in sedentary adults."],
        })

        output_file = tmp_path / "schema_test.json"
        data = json.loads(output_file.read_text())

        # Required keys
        assert "source" in data
        assert "ingested_at" in data
        assert "relevance_tags" in data
        assert "findings" in data

        # Correct types
        assert isinstance(data["relevance_tags"], list)
        assert isinstance(data["findings"], list)

        # filename must NOT appear in the JSON body
        assert "filename" not in data

        # Values round-trip correctly
        assert data["source"] == "Omega-3 and HDL — Smith et al. 2026"
        assert data["ingested_at"] == "2026-06-22"
        assert data["relevance_tags"] == ["hdl", "ldl"]
        assert len(data["findings"]) == 1
