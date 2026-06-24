"""
Telegram handler for document (PDF) uploads.

Flow:
  1. Download PDF bytes from Telegram
  2. Invoke OrchestratorAgent to classify (lab report vs research article)
     via route_to_agent tool call
  3. Dispatch to HealthExtractorAgent or KnowledgeIngestorAgent
  4. Handle GraphInterrupt from HealthExtractorAgent (confirm_with_user)
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage

from bot.cache import clear_paused_agent, set_paused_agent
from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def extract_routing_from_state(result_state: dict) -> str | None:
    """
    Scan result messages for a route_to_agent tool call.
    Returns the agent_name arg string, or None if no routing was signalled.
    """
    for msg in result_state.get("messages", []):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "route_to_agent":
                    return tc["args"].get("agent_name")
    return None


def _make_pdf_state(b64_pdf: str, filename: str, instruction: str) -> dict:
    return {
        "input_type": "pdf",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "messages": [HumanMessage(content=[
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64_pdf,
                },
            },
            {"type": "text", "text": instruction},
        ])],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }


async def handle_document(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    """
    Called for all document uploads. Processes PDFs only.
    """
    from langgraph.errors import GraphInterrupt
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.agents.agent_loader import AGENT_REGISTRY
    from bot.agents.tool_registry import AGENT_NAME_TO_TRIGGER

    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    document = update.message.document
    if document.mime_type != "application/pdf":
        await update.message.reply_text("I can only process PDF files — try again with a PDF!")
        return

    await update.message.reply_text("Got your PDF — analyzing it now... 📄")

    tg_file = await document.get_file()
    file_bytes: bytearray = await tg_file.download_as_bytearray()
    b64_pdf = base64.b64encode(bytes(file_bytes)).decode()
    filename: str = document.file_name or "upload.pdf"

    orchestrator = AGENT_REGISTRY.get("pdf")
    if orchestrator is None:
        await update.message.reply_text("Agent not ready — please try again in a moment.")
        return

    loop = asyncio.get_running_loop()

    # Step 1: classify the PDF
    classify_state = _make_pdf_state(
        b64_pdf, filename,
        f"Classify this document (filename: {filename}). Is it a lab report or research article? "
        "Call route_to_agent with 'HealthExtractorAgent' for lab reports, "
        "'KnowledgeIngestorAgent' for research articles."
    )
    classify_result = await loop.run_in_executor(None, lambda: orchestrator.invoke(classify_state))
    agent_name = extract_routing_from_state(classify_result)

    if agent_name is None:
        await update.message.reply_text(
            "Hmm, I couldn't figure out what type of document that is. "
            "Is it a lab report or a research article?"
        )
        return

    trigger = AGENT_NAME_TO_TRIGGER.get(agent_name)
    specialist = AGENT_REGISTRY.get(trigger) if trigger else None
    if specialist is None:
        await update.message.reply_text(f"Routing error — no agent found for {agent_name}.")
        return

    # Step 2: invoke the specialist
    if agent_name == "HealthExtractorAgent":
        specialist_state = _make_pdf_state(
            b64_pdf, filename,
            "Extract the lab values from this health report: A1C, LDL, HDL, triglycerides, "
            "medications, and BMI. Then call confirm_with_user with the extracted values for confirmation."
        )
        thread_id = f"health-extract-{TELEGRAM_CHAT_ID}"
    else:
        specialist_state = _make_pdf_state(
            b64_pdf, filename,
            "Extract the key findings from this research article and save them to the knowledge base."
        )
        thread_id = None  # KnowledgeIngestorAgent doesn't need checkpointing

    try:
        await loop.run_in_executor(
            None, lambda: specialist.invoke(specialist_state, thread_id=thread_id)
        )
        clear_paused_agent()

    except GraphInterrupt as exc:
        # HealthExtractorAgent paused at confirm_with_user — show confirmation keyboard
        interrupt_msg = exc.interrupts[0].value if exc.interrupts else "Does this look right?"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Confirm ✅", callback_data="labconfirm:yes"),
            InlineKeyboardButton("Re-upload 🔄", callback_data="labconfirm:reupload"),
        ]])
        await update.message.reply_text(interrupt_msg, reply_markup=keyboard)
        set_paused_agent("lab_report")


async def handle_labconfirm_callback(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Handle [Confirm] / [Re-upload] taps from HealthExtractorAgent confirmation."""
    from langgraph.types import Command
    from bot.agents.agent_loader import AGENT_REGISTRY

    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    choice = query.data.split(":", 1)[1]  # "yes" or "reupload"
    agent = AGENT_REGISTRY.get("lab_report")
    if agent is None:
        await query.edit_message_text("Agent not available — please try again.")
        return

    thread_id = f"health-extract-{TELEGRAM_CHAT_ID}"
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: agent.graph.invoke(
            Command(resume=choice),
            config={"configurable": {"thread_id": thread_id}},
        )
    )
    clear_paused_agent()
