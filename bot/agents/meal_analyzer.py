"""
MealAnalyzerAgent — analyzes food photos, saves meal logs.

Thin wrapper: all logic lives in prompts/meal_analyzer.txt and tool_registry.py.
Config (model, tools, context) is declared in bot/agents/configs/meal_analyzer.yaml.
"""

from pathlib import Path

from bot.agents.agent_loader import load_agent
from bot.agents.base_agent import BaseAgent

_CONFIG = Path(__file__).parent / "configs" / "meal_analyzer.yaml"


class MealAnalyzerAgent(BaseAgent):
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
