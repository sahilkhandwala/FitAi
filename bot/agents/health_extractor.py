"""
HealthExtractorAgent — extracts lab values from PDF, saves health profile.

Thin wrapper: all logic lives in prompts/health_extractor.txt and tool_registry.py.
Config (model, tools) is declared in bot/agents/configs/health_extractor.yaml.
No context injection — this agent reads a raw PDF, not Sahil's existing profile.
"""

from pathlib import Path

from bot.agents.agent_loader import load_agent
from bot.agents.base_agent import BaseAgent

_CONFIG = Path(__file__).parent / "configs" / "health_extractor.yaml"


class HealthExtractorAgent(BaseAgent):
    def __init__(self):
        agent = load_agent(_CONFIG)
        super().__init__(
            model=agent.model_str,
            max_tokens=agent.max_tokens,
            recursion_limit=agent.recursion_limit,
            system_prompt=agent.system_prompt,
            tools=agent.tools,
            context_keys=agent.context_keys,
        )
