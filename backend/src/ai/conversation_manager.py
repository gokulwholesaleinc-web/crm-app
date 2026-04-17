"""Conversation memory management for the AI assistant."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.models import AIConversation, AIUserPreferences

logger = logging.getLogger(__name__)

WORKING_MEMORY_SIZE = 20
SUMMARY_THRESHOLD = 20


class AIConversationManager:
    def __init__(self, db: AsyncSession, openai_client=None):
        self.db = db
        self.client = openai_client

    async def get_user_preferences(self, user_id: int) -> AIUserPreferences | None:
        result = await self.db.execute(
            select(AIUserPreferences).where(AIUserPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_conversation_history(
        self, user_id: int, session_id: str | None = None
    ) -> list[dict[str, str]]:
        if not session_id:
            return []

        result = await self.db.execute(
            select(AIConversation)
            .where(
                AIConversation.user_id == user_id,
                AIConversation.session_id == session_id,
            )
            .order_by(AIConversation.created_at.asc())
        )
        messages = result.scalars().all()

        if not messages:
            return []

        if len(messages) <= WORKING_MEMORY_SIZE:
            return [{"role": m.role, "content": m.content} for m in messages]

        older = messages[:-WORKING_MEMORY_SIZE]
        recent = messages[-WORKING_MEMORY_SIZE:]

        summary = await self.summarize_messages(older)

        history = []
        if summary:
            history.append({
                "role": "system",
                "content": f"Summary of earlier conversation: {summary}",
            })

        history.extend({"role": m.role, "content": m.content} for m in recent)
        return history

    async def summarize_messages(self, messages: list[AIConversation]) -> str | None:
        if not self.client or not messages:
            return None

        conversation_text = "\n".join(f"{m.role}: {m.content}" for m in messages)

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize this CRM assistant conversation concisely, preserving key entities, decisions, and context. Keep it under 200 words.",
                    },
                    {"role": "user", "content": conversation_text},
                ],
                max_tokens=300,
            )
            return response.choices[0].message.content
        except (OSError, RuntimeError, KeyError) as exc:
            logger.warning("Failed to summarize conversation: %s", exc)
            return None

    async def save_conversation(
        self, user_id: int, session_id: str | None, role: str, content: str
    ) -> None:
        msg = AIConversation(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
        )
        self.db.add(msg)
        await self.db.flush()
