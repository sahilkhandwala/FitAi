"""
AgentLoader — reads YAML configs from bot/agents/configs/ and builds AGENT_REGISTRY.

Usage (in main.py):
    from bot.agents.agent_loader import build_agent_registry, AGENT_REGISTRY
    AGENT_REGISTRY.update(build_agent_registry())

AGENT_REGISTRY maps trigger string → BaseAgent instance.
Multiple triggers for the same agent point to the same instance.

Context is loaded at startup (not per-invocation) and prepended to the system
prompt. This means context reflects DB state at bot startup time. For most
agents this is acceptable; DailySummaryAgent and WeeklyReportAgent run via
Prefect so they restart each time and always see fresh context.
"""

from pathlib import Path

import yaml

from config import (
    ANTHROPIC_MODEL_FAST,
    ANTHROPIC_MODEL_HEAVY,
    ANTHROPIC_MODEL_MID,
)
from bot.agents.base_agent import BaseAgent
from bot.agents.tool_registry import CONTEXT_LOADERS, TOOL_REGISTRY

# Maps config model names → resolved Anthropic model strings
MODEL_MAP: dict[str, str] = {
    # Shorthand names from YAML
    "claude-opus-4-8": ANTHROPIC_MODEL_HEAVY,
    "claude-sonnet-4-6": ANTHROPIC_MODEL_MID,
    "claude-haiku-4-5-20251001": ANTHROPIC_MODEL_FAST,
    # Env-var symbolic names (also accepted in YAML)
    "ANTHROPIC_MODEL_HEAVY": ANTHROPIC_MODEL_HEAVY,
    "ANTHROPIC_MODEL_MID": ANTHROPIC_MODEL_MID,
    "ANTHROPIC_MODEL_FAST": ANTHROPIC_MODEL_FAST,
}

# Prompts root relative to project root
_PROMPTS_ROOT = Path(__file__).parent.parent.parent  # project root


def load_agent(config_path: Path) -> BaseAgent:
    """
    Load a single agent from a YAML config file.

    Steps:
    1. Parse YAML
    2. Resolve model name via MODEL_MAP
    3. Load system prompt text from prompts/ file
    4. If config has 'context' keys, load each via CONTEXT_LOADERS and prepend to prompt
    5. Resolve tools list → actual @tool objects from TOOL_REGISTRY
    6. Return BaseAgent
    """
    config = yaml.safe_load(config_path.read_text())

    # 1. Resolve model
    model_key = config["model"]
    model = MODEL_MAP.get(model_key, model_key)  # fall through if already a full model string

    # 2. Load system prompt
    prompt_file = _PROMPTS_ROOT / config["prompt"]
    system_prompt = prompt_file.read_text()

    # 3. Validate context keys — don't load them here; BaseAgent loads fresh on each invocation
    context_keys = config.get("context", [])
    for key in context_keys:
        if key not in CONTEXT_LOADERS:
            raise ValueError(f"Unknown context key '{key}' in {config_path.name}")

    # 4. Resolve tools
    tool_names = config.get("tools", [])
    tools = []
    for name in tool_names:
        t = TOOL_REGISTRY.get(name)
        if t is None:
            raise ValueError(f"Unknown tool '{name}' in {config_path.name}")
        tools.append(t)

    return BaseAgent(
        model=model,
        max_tokens=config.get("max_tokens", 1024),
        recursion_limit=config.get("recursion_limit", 5),
        system_prompt=system_prompt,
        tools=tools,
        context_keys=context_keys,
        use_checkpointer=bool(config.get("checkpointer", False)),
    )


def build_agent_registry() -> dict[str, BaseAgent]:
    """
    Scan bot/agents/configs/ and build a trigger → BaseAgent registry.

    Multiple triggers for the same config file point to the same BaseAgent instance.
    Safe to call multiple times — returns a fresh dict each call.
    """
    configs_dir = Path(__file__).parent / "configs"
    registry: dict[str, BaseAgent] = {}

    for config_path in sorted(configs_dir.glob("*.yaml")):
        agent = load_agent(config_path)
        config = yaml.safe_load(config_path.read_text())
        for trigger in config.get("triggers", []):
            registry[trigger] = agent

    return registry


# Populated at startup via main.py calling build_agent_registry()
AGENT_REGISTRY: dict[str, BaseAgent] = {}
