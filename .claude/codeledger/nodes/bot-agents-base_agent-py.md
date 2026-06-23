# bot/agents/base_agent.py

## Summary
Defines AgentState (LangGraph TypedDict) and BaseAgent class — the shared LangGraph StateGraph wiring that all FitAi agents are built from. Constructs a START → call_model → [tool_node ↔ call_model loop] → END graph. Tools are handled natively via LangGraph ToolNode. Supports optional AsyncSqliteSaver checkpointing for multi-turn agents (HealthInsightsAgent).

## Functions
- BaseAgent.__init__(model, max_tokens, recursion_limit, system_prompt, tools, use_checkpointer) — creates ChatAnthropic LLM, binds tools, builds graph
- BaseAgent._build_graph() → StateGraph — constructs LangGraph with tool-call loop; attaches AsyncSqliteSaver if use_checkpointer=True; lazy-imports AsyncSqliteSaver to avoid hard dependency
- BaseAgent._call_model_node(state) → dict — LangGraph node that prepends SystemMessage and invokes the LLM
- BaseAgent.invoke(state, thread_id) → AgentState — runs graph synchronously with recursion_limit; passes thread_id in configurable for checkpointed agents

## Non-function code
- `AgentState` — TypedDict with fields: input_type, telegram_chat_id, messages, media_group_id, photos, analysis_result, next_agent

## Imports
- typing.TypedDict
- langchain_anthropic.ChatAnthropic
- langchain_core.messages (BaseMessage, SystemMessage)
- langgraph.graph (START, END, StateGraph)
- langgraph.prebuilt (ToolNode, tools_condition)
- (lazy) langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver
- (lazy) config.SQLITE_DB_PATH

## Imported by
- bot/agents/agent_loader.py — instantiates BaseAgent for each YAML config

## Tags
agents, langgraph, base, infrastructure, state

## Node path
bot/agents/base_agent.py
