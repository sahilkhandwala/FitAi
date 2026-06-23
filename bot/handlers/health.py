"""
Telegram handler for document (PDF) uploads.

Routes to HealthExtractorAgent (lab reports) or KnowledgeIngestorAgent
(research articles) based on OrchestratorAgent classification.

Routing only — no LLM calls, no DB access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


async def handle_document(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    """
    Called for all document uploads. Only processes PDFs.

    1. Reject if not the allowed chat_id
    2. Reject non-PDF files with a user-friendly message
    3. Download PDF bytes
    4. Route to HealthExtractorAgent or KnowledgeIngestorAgent via OrchestratorAgent
    """
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    document = update.message.document

    if document.mime_type != "application/pdf":
        await update.message.reply_text(
            "I can only process PDF files — try again with a PDF!"
        )
        return

    await update.message.reply_text("Got your PDF — analyzing it now...")

    # Download the file bytes
    tg_file = await document.get_file()
    file_bytes: bytearray = await tg_file.download_as_bytearray()
    filename: str = document.file_name or "upload.pdf"

    # TODO: call OrchestratorAgent to classify PDF type
    # The orchestrator inspects the filename and/or a text excerpt to decide:
    #   "lab_report"      → HealthExtractorAgent
    #   "research_article" → KnowledgeIngestorAgent
    #
    # agent_input = AgentState(
    #     input_type="pdf",
    #     telegram_chat_id=TELEGRAM_CHAT_ID,
    #     messages=[{
    #         "role": "user",
    #         "content": f"filename: {filename}\nbytes: <{len(file_bytes)} bytes>",
    #     }],
    #     media_group_id=None,
    #     photos=[],
    #     analysis_result=None,
    #     next_agent=None,
    # )
    # result = await orchestrator_agent.invoke(agent_input, pdf_bytes=file_bytes)
