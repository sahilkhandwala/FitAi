"""Unit tests for extract_routing_from_state helper (used in health handler)."""


def _make_ai_message_with_tool_call(agent_name: str):
    """Build a fake AIMessage that contains a route_to_agent tool call."""
    from langchain_core.messages import AIMessage

    return AIMessage(
        content="",
        tool_calls=[{"name": "route_to_agent", "args": {"agent_name": agent_name}, "id": "tc1"}],
    )


def test_extract_routing_finds_health_extractor():
    from bot.handlers.health import extract_routing_from_state

    msg = _make_ai_message_with_tool_call("HealthExtractorAgent")
    result = extract_routing_from_state({"messages": [msg]})
    assert result == "HealthExtractorAgent"


def test_extract_routing_finds_knowledge_ingestor():
    from bot.handlers.health import extract_routing_from_state

    msg = _make_ai_message_with_tool_call("KnowledgeIngestorAgent")
    result = extract_routing_from_state({"messages": [msg]})
    assert result == "KnowledgeIngestorAgent"


def test_extract_routing_returns_none_when_no_route_call():
    from langchain_core.messages import AIMessage
    from bot.handlers.health import extract_routing_from_state

    msg = AIMessage(content="Just a plain response, no routing.")
    result = extract_routing_from_state({"messages": [msg]})
    assert result is None


def test_extract_routing_returns_none_for_empty_messages():
    from bot.handlers.health import extract_routing_from_state

    result = extract_routing_from_state({"messages": []})
    assert result is None
