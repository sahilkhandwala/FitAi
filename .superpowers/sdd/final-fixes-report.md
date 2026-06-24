# Final Fixes Report

## Status: DONE

## Fixes Applied

### C1: Interrupt Detection (LangGraph 1.0+)

**Problem:** LangGraph 1.0+ returns a dict with `__interrupt__` key instead of raising `GraphInterrupt`. All `try/except GraphInterrupt` blocks were dead code.

**Files changed:**
- `bot/handlers/meal.py` — `handle_meal_type_callback`: replaced `try/except GraphInterrupt` with check on `result.get("__interrupt__")`
- `bot/handlers/health.py` — `handle_document`: replaced `try/except GraphInterrupt` with check on `result.get("__interrupt__")`
- `bot/handlers/commands.py` — `handle_text_message`: fixed all three interrupt sites (paused agent resume, orchestrator invoke, HealthInsightsAgent invoke) and removed dead `GraphInterrupt` import

**Resume paths** (`Command(resume=...)` in `handle_labconfirm_callback`, `handle_websearch_callback`, `handle_text_message`): `graph.invoke(Command(resume=value), config=...)` API is unchanged in LangGraph 1.0. Resume return values now also checked for `__interrupt__` in the text message resume path.

### C2: Checkpointer

**Problem:** `AsyncSqliteSaver` module no longer exists; `SqliteSaver.from_conn_string()` is a `@contextmanager` (cannot be assigned directly).

**Fix in `bot/agents/base_agent.py`:**
- Switched from `AsyncSqliteSaver` to `SqliteSaver` (sync, matches `graph.invoke()` usage throughout)
- Construct via `sqlite3.connect(path, check_same_thread=False)` + `SqliteSaver(conn)` directly — avoids the context-manager pitfall
- Uses `SQLITE_DB_PATH + "-checkpoints.db"` so checkpoint DB is separate from main WAL DB
- `check_same_thread=False` required because all `agent.invoke()` calls run in `loop.run_in_executor(None, ...)` thread pool

**Dependency fix:** `langgraph-checkpoint-sqlite 3.1.0` requires `langgraph-checkpoint>=4.1.0` which conflicts with `langgraph 1.0.4` (`requires checkpoint<4.0.0`). Downgraded to `langgraph-checkpoint-sqlite<3.0.0` (installed 2.0.11 + checkpoint 2.1.2) which satisfies all constraints. Added pin to `requirements.txt`.

### I1: Register `handle_profile_update`

**Problem:** `handle_profile_update` was defined in `commands.py` but never registered in `main.py`.

**Fix:**
- `bot/main.py`: imported `handle_profile_update` and registered `CommandHandler("profileupdate", handle_profile_update)`
- `bot/handlers/commands.py` `_format_profile`: updated hint from "Send /profile update to add details" → "Use /profileupdate to add details"

## Tests

217 passed, 2 skipped, 1 warning (LangChainPendingDeprecationWarning — cosmetic, from langgraph internals)

## Concerns

None blocking. One note: the dependency resolution produces a `pip check`-clean result for langgraph packages but the shared Anaconda environment has pre-existing unrelated conflicts (crewai, streamlit, firebase-admin, fastmcp, langchain-openai) that are not caused by these changes and do not affect this project.
