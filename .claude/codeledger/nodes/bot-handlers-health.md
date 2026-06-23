# health.py

## Summary
Telegram document handler for PDF uploads. Validates that the file is a PDF, downloads bytes, and stubs routing to HealthExtractorAgent or KnowledgeIngestorAgent via OrchestratorAgent. Non-PDF uploads receive a user-friendly rejection message. Agent routing is a TODO for Wave 2.

## Functions
- handle_document(update, context) — async Telegram handler: rejects non-TELEGRAM_CHAT_ID, rejects non-PDF mime types, downloads file bytes via get_file().download_as_bytearray(), stubs OrchestratorAgent classification call

## Non-function code
- `from __future__ import annotations` + `TYPE_CHECKING` guard — keeps `telegram` imports lazy

## Imports
- config.TELEGRAM_CHAT_ID — single-user auth guard
- telegram (TYPE_CHECKING) — Update (lazy)
- telegram.ext (TYPE_CHECKING) — ContextTypes (lazy)

## Imported by
- bot/main.py — registers handle_document for filters.Document.PDF

## Tags
telegram, handler, pdf, routing, health

## Node path
bot/handlers/health.py
