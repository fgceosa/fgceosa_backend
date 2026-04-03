import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import HTTPException
from sqlmodel import Session

from app import chat_repository
from app.services.requesty_ai import requesty_service
from app.models import AIChatMessagePublic, AIChatMessageResponse

logger = logging.getLogger(__name__)

class ChatService:
    @staticmethod
    async def process_user_message(
        session: Session,
        user_id: UUID,
        chat_id: UUID,
        message_content: str,
        model: Optional[str] = None
    ) -> AIChatMessageResponse:
        """
        Process a user message: save it, get AI response, save response, and update chat.
        """
        # 1. Verify chat ownership
        chat = chat_repository.get_chat_by_id(session, chat_id, user_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        # 2. Get history for context
        existing_messages = chat_repository.get_messages_by_chat_id(session, chat_id)
        
        # 3. Save user message
        user_message = chat_repository.create_message(
            session=session,
            chat_id=chat_id,
            role="user",
            content=message_content
        )

        try:
            # 4. Prepare context for AI
            logger.info(f"Processing message for chat {chat_id}, model: {model}")
            
            ai_context = [
                {"role": msg.role, "content": msg.content}
                for msg in existing_messages
            ]
            ai_context.append({"role": "user", "content": message_content})

            # 5. Get AI response
            logger.info(f"Requesting AI response for chat {chat_id}...")
            
            # Use organization credits if user belongs to one
            organization_id = None
            if hasattr(chat, "user") and chat.user:
                # We need to find the user's organization. 
                # For now, we'll fetch it from the database session.
                from app.models import OrganizationMember
                from sqlmodel import select
                stmt = select(OrganizationMember).where(OrganizationMember.user_id == user_id)
                membership = session.exec(stmt).first()
                if membership:
                    organization_id = membership.organization_id

            ai_result = await requesty_service.generate_response(
                ai_context,
                model=model,
                session=session,
                user_id=user_id,
                organization_id=organization_id
            )
            logger.info(f"AI response received for chat {chat_id}")

            # 6. Save assistant response
            assistant_message = chat_repository.create_message(
                session=session,
                chat_id=chat_id,
                role="assistant",
                content=ai_result["content"],
                tokens_used=ai_result.get("tokens_used"),
                model=ai_result.get("model")
            )

            # 7. Update chat timestamp and title if new
            chat_repository.update_chat_timestamp(session, chat)
            
            if len(existing_messages) == 0:
                logger.info(f"Generating title for new chat {chat_id}...")
                try:
                    new_title = await requesty_service.generate_chat_title(
                        message_content,
                        session=session,
                        user_id=user_id
                    )
                    chat_repository.update_chat_title(session, chat, new_title)
                    logger.info(f"Updated title for chat {chat_id}: {new_title}")
                except Exception as title_err:
                    logger.warning(f"Title generation failed for chat {chat_id}: {title_err}")
                    pass # title generation is non-critical

            return AIChatMessageResponse(
                user_message=AIChatMessagePublic.model_validate(user_message),
                assistant_message=AIChatMessagePublic.model_validate(assistant_message)
            )

        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Critical error in process_user_message:\n{error_details}")
            return ChatService._handle_ai_error(e)

    @staticmethod
    def _handle_ai_error(e: Exception) -> Any:
        error_message = str(e)
        
        if "Rate limit exceeded" in error_message or "429" in error_message:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": "You've made too many requests. Please wait a moment and try again.",
                    "retry_after": 60
                }
            )
            
        # Log the actual exception type for debugging
        logger.error(f"AI Error ({type(e).__name__}): {error_message}")
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate AI response: {error_message if error_message else type(e).__name__}"
        )

chat_service = ChatService()
