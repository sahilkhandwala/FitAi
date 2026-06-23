# bot/agents/agent_loader.py

## Summary
Reads YAML config files from bot/agents/configs/ and builds the AGENT_REGISTRY dict mapping trigger strings to BaseAgent instances. Resolves model names via MODEL_MAP, loads system prompt text, prepends context blocks via CONTEXT_LOADERS if specified in config, resolves tool names via TOOL_REGISTRY, and instantiates BaseAgent. AGENT_REGISTRY is empty at import; must be populated by calling build_agent_registry() at startup.

## Functions
- load_agent(config_path) → BaseAgent — loads one agent from a YAML config: resolves model, reads prompt file, prepends context blocks, resolves tools, returns BaseAgent instance
- build_agent_registry() → dict[str, BaseAgent] — scans configs/ directory, calls load_agent for each YAML, returns trigger → BaseAgent dict; multiple triggers map to the same instance

## Non-function code
- `MODEL_MAP` — dict mapping shorthand model names and env-var symbolic names to actual Anthropic model strings
- `_PROMPTS_ROOT` — Path to project root (three parents up from this file)
- `AGENT_REGISTRY` — empty dict at import; populated by main.py calling build_agent_registry()

## Imports
- pathlib.Path
- yaml
- config (ANTHROPIC_MODEL_FAST, ANTHROPIC_MODEL_HEAVY, ANTHROPIC_MODEL_MID)
- bot.agents.base_agent.BaseAgent
- bot.agents.tool_registry (CONTEXT_LOADERS, TOOL_REGISTRY)

## Imported by
- main.py (planned) — calls build_agent_registry() at startup and populates AGENT_REGISTRY
- bot/handlers/ (planned) — imports AGENT_REGISTRY for routing

## Tags
agents, loader, registry, yaml, config, infrastructure

## Node path
bot/agents/agent_loader.py
