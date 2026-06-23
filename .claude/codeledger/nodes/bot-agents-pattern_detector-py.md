# bot/agents/pattern_detector.py

## Summary
Contains two pure logic functions for pattern escalation/dedup (used by unit tests) plus PatternDetectorAgent — a composition wrapper around BaseAgent that loads pattern_detector.yaml. The agent has no context injection; it uses tools query_last_7_days, get_sent_callouts, and send_telegram_msg to detect behavioral streaks and send callouts.

## Functions
- get_escalation_tier(streak_days) → str — returns 'informational' (1-3), 'firm' (4-6), or 'warning' (7+) based on streak length
- should_send_callout(pattern_type, date, sent_callouts) → bool — returns True if pattern_type not already in sent_callouts list; date param accepted for interface consistency
- PatternDetectorAgent.__init__() — lazy-imports BaseAgent and load_agent, loads pattern_detector.yaml, delegates to BaseAgent via composition; exposes model_str, max_tokens, recursion_limit, system_prompt, tools, graph
- PatternDetectorAgent.invoke(state, thread_id) → AgentState — delegates to BaseAgent.invoke

## Non-function code
None at module level.

## Imports
None at module level. BaseAgent, load_agent, Path imported lazily inside PatternDetectorAgent.__init__.

## Imported by
- tests/unit/test_pattern_logic.py — imports get_escalation_tier, should_send_callout
- tests/integration/test_pattern_detector.py — imports PatternDetectorAgent, get_escalation_tier, should_send_callout

## Tags
agents, patterns, langgraph, haiku, streak, callout

## Node path
bot/agents/pattern_detector.py
