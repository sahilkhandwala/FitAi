"""
BaseAgent — shared LangGraph StateGraph wiring for all FitAi agents.

All specialist agents are built by AgentLoader using this class.
BaseAgent does NOT load context — that is done by AgentLoader before building
the instance (context is prepended to system_prompt at load time, so it reflects
DB state at startup, not at each invocation).

Graph structure:
    START → call_model → [tool_node ↔ call_model loop] → END

Tools are handled natively by LangGraph's ToolNode — the model emits tool calls,
ToolNode executes them, and the loop continues until the model emits a plain message.
"""

from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition


class AgentState(TypedDict):
    input_type: str           # "photo" | "pdf" | "command" | "cron" | "text"
    telegram_chat_id: int
    messages: list            # LangChain message format (HumanMessage, AIMessage, etc.)
    media_group_id: str | None
    photos: list              # list of file_id strings (buffered from TTLCache)
    analysis_result: dict | None
    next_agent: str | None


class BaseAgent:
    """
    Shared LangGraph wiring for all FitAi agents.

    Args:
        model: Full Anthropic model string (e.g. "claude-haiku-4-5-20251001")
        max_tokens: Max output tokens for this agent
        recursion_limit: LangGraph recursion limit (controls tool-call loop depth)
        system_prompt: System prompt text (the static prompt from prompts/*.txt)
        tools: List of @tool-decorated callables
        context_keys: List of context keys to load fresh from DB on each invocation
                      (e.g. ["health_profile", "knowledge_base"]). Loaded via
                      CONTEXT_LOADERS at call time so they never go stale.
        use_checkpointer: If True, attaches AsyncSqliteSaver for multi-turn memory
    """

    def __init__(
        self,
        model: str,
        max_tokens: int,
        recursion_limit: int,
        system_prompt: str,
        tools: list,
        context_keys: list[str] | None = None,
        use_checkpointer: bool = False,
    ) -> None:
        self.model_str = model
        self.max_tokens = max_tokens
        self.recursion_limit = recursion_limit
        self.system_prompt = system_prompt  # static base prompt
        self.context_keys = context_keys or []
        self.tools = tools
        self.use_checkpointer = use_checkpointer

        self._llm = ChatAnthropic(
            model=model,
            max_tokens=max_tokens,
        )
        self._llm_with_tools = self._llm.bind_tools(tools) if tools else self._llm

        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct the LangGraph StateGraph with tool-call loop."""
        builder = StateGraph(AgentState)

        # Nodes
        builder.add_node("call_model", self._call_model_node)
        if self.tools:
            builder.add_node("tool_node", ToolNode(self.tools))

        # Edges
        builder.add_edge(START, "call_model")

        if self.tools:
            builder.add_conditional_edges(
                "call_model",
                tools_condition,
                {
                    "tools": "tool_node",
                    END: END,
                },
            )
            builder.add_edge("tool_node", "call_model")
        else:
            builder.add_edge("call_model", END)

        # Checkpointer for multi-turn agents (HealthInsightsAgent, MealAnalyzerAgent, HealthExtractorAgent)
        if self.use_checkpointer:
            # Lazy import — langgraph-checkpoint-sqlite is optional
            try:
                import sqlite3
                from langgraph.checkpoint.sqlite import SqliteSaver
                from config import SQLITE_DB_PATH

                # Use a separate DB file for checkpoints so WAL-mode nutrition.db is unaffected.
                # check_same_thread=False is required: graph.invoke() runs in thread-pool executors.
                checkpoints_path = SQLITE_DB_PATH + "-checkpoints.db"
                conn = sqlite3.connect(checkpoints_path, check_same_thread=False)
                checkpointer = SqliteSaver(conn)
                return builder.compile(checkpointer=checkpointer)
            except ImportError:
                # If the optional package is missing, fall back to no checkpointer
                pass

        return builder.compile()

    def _build_full_system_prompt(self) -> str:
        """
        Build the complete system prompt by loading fresh context from DB.
        Called on every invocation so context (health profile, guidance, etc.)
        is always current — never stale from bot startup.
        """
        if not self.context_keys:
            return self.system_prompt

        from bot.agents.tool_registry import CONTEXT_LOADERS
        from sqlalchemy.exc import OperationalError
        blocks = []
        for key in self.context_keys:
            loader = CONTEXT_LOADERS.get(key)
            if loader is None:
                continue
            try:
                blocks.append(loader())
            except (RuntimeError, OperationalError):
                blocks.append(f"=== {key.upper().replace('_', ' ')} ===\nNot available.\n")

        return "\n".join(blocks) + "\n" + self.system_prompt

    def _call_model_node(self, state: AgentState) -> dict:
        """LangGraph node: prepend fresh system prompt (with live context) and invoke the LLM."""
        messages = state["messages"]

        # Build system prompt fresh each invocation so context is never stale
        full_prompt = self._build_full_system_prompt()

        # Prepend system message if not already present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=full_prompt)] + list(messages)

        response = self._llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def invoke(self, state: AgentState, thread_id: str | None = None) -> AgentState:
        """
        Run the agent graph synchronously.

        Args:
            state: Initial AgentState
            thread_id: Used as LangGraph thread_id for checkpointed agents.
                       Required for HealthInsightsAgent multi-turn continuations.

        Returns:
            Final AgentState after all tool calls complete.
        """
        config: dict = {"recursion_limit": self.recursion_limit}
        if thread_id is not None:
            config["configurable"] = {"thread_id": thread_id}

        return self.graph.invoke(state, config=config)
