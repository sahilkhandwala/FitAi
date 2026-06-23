"""
PatternDetectorAgent — streak and pattern detection from meal and health logs.

Contains:
- get_escalation_tier / should_send_callout — pure logic functions (tested in unit tests)
- PatternDetectorAgent — LangGraph agent that detects streaks and sends callouts
"""


def get_escalation_tier(streak_days: int) -> str:
    """
    Return the escalation tier for a pattern callout based on consecutive days.

    Day 1-3  → 'informational'
    Day 4-6  → 'firm'
    Day 7+   → 'warning'
    """
    if streak_days >= 7:
        return "warning"
    elif streak_days >= 4:
        return "firm"
    else:
        return "informational"


def should_send_callout(
    pattern_type: str, date: str, sent_callouts: list[str]
) -> bool:
    """
    Return True if this pattern_type has not already been sent today.
    sent_callouts is the list of pattern_type strings already sent on this date.
    The date parameter is accepted for interface consistency but not used here —
    dedup is based on the sent_callouts list, which is already filtered by date.
    """
    return pattern_type not in sent_callouts


class PatternDetectorAgent:
    """LangGraph agent that detects behavioral streaks and sends callouts."""

    def __init__(self):
        from bot.agents.agent_loader import load_agent
        from bot.agents.base_agent import BaseAgent
        from pathlib import Path

        agent = load_agent(Path("bot/agents/configs/pattern_detector.yaml"))
        self._base = BaseAgent(
            model=agent.model_str,
            max_tokens=agent.max_tokens,
            recursion_limit=agent.recursion_limit,
            system_prompt=agent.system_prompt,
            tools=agent.tools,
            context_keys=agent.context_keys,
        )
        self.model_str = self._base.model_str
        self.max_tokens = self._base.max_tokens
        self.recursion_limit = self._base.recursion_limit
        self.system_prompt = self._base.system_prompt
        self.context_keys = self._base.context_keys
        self.tools = self._base.tools
        self.graph = self._base.graph

    def invoke(self, state, thread_id=None):
        return self._base.invoke(state, thread_id=thread_id)
