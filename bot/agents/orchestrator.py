"""OrchestratorAgent — routes all real-time Telegram messages."""

from pathlib import Path

from bot.agents.base_agent import BaseAgent
from bot.agents.agent_loader import load_agent


class OrchestratorAgent(BaseAgent):
    def __init__(self):
        agent = load_agent(Path("bot/agents/configs/orchestrator.yaml"))
        super().__init__(
            model=agent.model_str,
            max_tokens=agent.max_tokens,
            recursion_limit=agent.recursion_limit,
            system_prompt=agent.system_prompt,
            tools=agent.tools,
            context_keys=agent.context_keys,
        )
