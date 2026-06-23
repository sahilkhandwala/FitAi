"""HealthInsightsAgent — conversational health symptom Q&A (Opus 4.8, multi-turn)."""
from pathlib import Path

from bot.agents.base_agent import BaseAgent
from bot.agents.agent_loader import load_agent

_CONFIG = Path(__file__).parent / "configs" / "health_insights.yaml"


class HealthInsightsAgent(BaseAgent):
    def __init__(self):
        agent = load_agent(_CONFIG)
        super().__init__(
            model=agent.model_str,
            max_tokens=agent.max_tokens,
            recursion_limit=agent.recursion_limit,
            system_prompt=agent.system_prompt,
            tools=agent.tools,
            context_keys=agent.context_keys,
            use_checkpointer=agent.use_checkpointer,  # True for multi-turn
        )
