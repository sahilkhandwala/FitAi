# bot/agents/knowledge_ingestor.py

## Summary
Thin wrapper that instantiates KnowledgeIngestorAgent by loading the YAML config from bot/agents/configs/knowledge_ingestor.yaml via load_agent, then delegates all state and graph construction to BaseAgent. Processes research article PDFs via the save_to_knowledge_base tool using Claude Sonnet.

## Functions
- KnowledgeIngestorAgent.__init__() — calls load_agent with knowledge_ingestor.yaml, passes resolved model/tokens/prompt/tools to BaseAgent.__init__

## Non-function code
N/A

## Imports
- pathlib.Path
- bot.agents.base_agent.BaseAgent
- bot.agents.agent_loader.load_agent

## Imported by
- tests/integration/test_knowledge_ingestor.py — tested here

## Tags
agents, knowledge-ingestor, langgraph, sonnet, pdf

## Node path
bot/agents/knowledge_ingestor.py
