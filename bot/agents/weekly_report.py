"""WeeklyReportAgent — Sunday 8pm comprehensive weekly health report (Opus 4.8)."""
from pathlib import Path

from bot.agents.base_agent import BaseAgent
from bot.agents.agent_loader import load_agent

_CONFIG = Path(__file__).parent / "configs" / "weekly_report.yaml"


class WeeklyReportAgent(BaseAgent):
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
