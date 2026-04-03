
import logging
import uuid
import json
import time
import base64
from typing import List, Optional, Any, Dict
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException, status
from sqlmodel import Session, select, func, col, or_
from sqlalchemy import text
import httpx

from app.models import User
from app.api.deps import CurrentUser
from app.copilot.models import (
    Copilot, CopilotConversation, CopilotMessage, CopilotDocument, CopilotDocumentChunk
)
from app.copilot.schemas import (
    ConversationCreate, ConversationUpdate, ConversationPublic, ConversationsPublic,
    MessagePublic, MessagesPublic, SendMessageRequest, SendMessageResponse, MessageFeedback
)
from app.services.requesty_ai import requesty_service
from app.copilot.rag.embeddings import generate_embeddings
from app.utils.permissions import user_has_permission

logger = logging.getLogger(__name__)

class CopilotChatService:
    async def create_conversation(
        self,
        session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser,
        conversation_in: Optional[ConversationCreate] = None
    ) -> CopilotConversation:
        copilot = session.get(Copilot, copilot_id)
        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")

        if copilot.visibility == "private" and copilot.created_by != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")

        title = "New Conversation"
        context = {}
        if conversation_in:
            title = conversation_in.title or title
            context = conversation_in.context or context

        conversation = CopilotConversation(
            copilot_id=copilot_id,
            user_id=user.id,
            title=title,
            context=context,
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        return conversation

    async def list_conversations(
        self,
        session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser,
        skip: int = 0,
        limit: int = 50,
        is_active: Optional[bool] = None
    ) -> ConversationsPublic:
        statement = (
            select(CopilotConversation)
            .where(
                CopilotConversation.copilot_id == copilot_id,
                CopilotConversation.user_id == user.id,
            )
        )

        if is_active is not None:
            statement = statement.where(CopilotConversation.is_active == is_active)

        count_statement = select(func.count()).select_from(statement.subquery())
        total = session.exec(count_statement).one()

        statement = statement.order_by(col(CopilotConversation.updated_at).desc()).offset(skip).limit(limit)
        conversations = session.exec(statement).all()

        return ConversationsPublic(conversations=conversations, total=total)

    async def get_conversation(
        self,
        session: Session,
        conversation_id: uuid.UUID,
        user: CurrentUser
    ) -> CopilotConversation:
        conversation = session.get(CopilotConversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.user_id != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")

        return conversation

    async def update_conversation(
        self,
        session: Session,
        conversation_id: uuid.UUID,
        user: CurrentUser,
        conversation_in: ConversationUpdate
    ) -> CopilotConversation:
        conversation = session.get(CopilotConversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.user_id != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")

        update_data = conversation_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(conversation, field, value)

        conversation.updated_at = datetime.now(timezone.utc)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        return conversation

    async def delete_conversation(
        self,
        session: Session,
        conversation_id: uuid.UUID,
        user: CurrentUser
    ) -> None:
        conversation = session.get(CopilotConversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.user_id != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")

        session.delete(conversation)
        session.commit()

    async def list_messages(
        self,
        session: Session,
        conversation_id: uuid.UUID,
        user: CurrentUser,
        skip: int = 0,
        limit: int = 100
    ) -> MessagesPublic:
        conversation = session.get(CopilotConversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.user_id != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")

        statement = (
            select(CopilotMessage)
            .where(CopilotMessage.conversation_id == conversation_id)
            .order_by(CopilotMessage.created_at)
            .offset(skip)
            .limit(limit)
        )
        messages = session.exec(statement).all()

        count_statement = select(func.count()).select_from(CopilotMessage).where(
            CopilotMessage.conversation_id == conversation_id
        )
        total = session.exec(count_statement).one()

        # Convert to Pydantic models
        msg_list = [
            MessagePublic(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                attachments=msg.attachments or [],
                message_metadata=msg.message_metadata or {},
                model_used=msg.model_used,
                tokens_used=msg.tokens_used,
                cost=msg.cost,
                response_time_ms=msg.response_time_ms,
                feedback_rating=msg.feedback_rating,
                feedback_comment=msg.feedback_comment,
                created_at=msg.created_at,
            )
            for msg in messages
        ]

        return MessagesPublic(messages=msg_list, total=total)

    async def submit_feedback(
        self,
        session: Session,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user: CurrentUser,
        feedback: MessageFeedback
    ) -> dict:
        conversation = session.get(CopilotConversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.user_id != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")

        message = session.get(CopilotMessage, message_id)
        if not message or message.conversation_id != conversation_id:
            raise HTTPException(status_code=404, detail="Message not found")

        message.feedback_rating = feedback.rating
        message.feedback_comment = feedback.comment
        session.add(message)
        session.commit()
        return {"status": "success", "message": "Feedback submitted"}

    async def update_message(
        self,
        session: Session,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user: CurrentUser,
        content: str
    ) -> CopilotMessage:
        conversation = session.get(CopilotConversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.user_id != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")

        message = session.get(CopilotMessage, message_id)
        if not message or message.conversation_id != conversation_id:
            raise HTTPException(status_code=404, detail="Message not found")

        message.content = content
        session.add(message)
        session.commit()
        session.refresh(message)
        return message

    async def delete_messages_after(
        self,
        session: Session,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user: CurrentUser
    ) -> dict:
        conversation = session.get(CopilotConversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.user_id != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")

        target_message = session.get(CopilotMessage, message_id)
        if not target_message or target_message.conversation_id != conversation_id:
            raise HTTPException(status_code=404, detail="Message not found")

        # Delete all messages with created_at > target_message.created_at
        statement = (
            text("DELETE FROM copilot_message WHERE conversation_id = :conv_id AND created_at > :target_time")
        )
        session.execute(statement, {"conv_id": conversation_id, "target_time": target_message.created_at})
        
        # Also need to update conversation message count
        # Re-fetch count
        count_statement = select(func.count()).select_from(CopilotMessage).where(CopilotMessage.conversation_id == conversation_id)
        new_count = session.exec(count_statement).one()
        conversation.message_count = new_count
        
        session.add(conversation)
        session.commit()
        
        return {"status": "success", "message": "Subsequent messages deleted", "new_count": new_count}


    async def send_message(
        self,
        session: Session,
        main_session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser,
        message_in: SendMessageRequest
    ) -> SendMessageResponse:
        # Get copilot
        copilot = session.get(Copilot, copilot_id)
        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")

        # Status Checks
        is_owner = copilot.created_by == user.id
        is_superadmin = user.is_superuser

        # 1. Disabled Check
        if copilot.status == "disabled":
            # Only superadmins in preview mode can use disabled copilots
            if not (is_superadmin and message_in.admin_preview):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail="This copilot is currently disabled and cannot be used."
                )
        
        # Check workspace/share access early to determine if we can bypass Draft/Inactive checks
        from app.services.copilot_service import copilot_service
        org_id, org_role, ws_ids = await copilot_service._get_user_context(main_session, user)
        
        has_access = False
        if is_owner or is_superadmin:
            has_access = True
        else:
            # Share check
            from app.copilot.models import CopilotShare
            share = session.exec(
                select(CopilotShare).where(
                    CopilotShare.copilot_id == copilot_id,
                    or_(CopilotShare.user_id == user.id, CopilotShare.email == user.email)
                )
            ).first()
            if share:
                has_access = True
            
            # Workspace/Org Check
            elif org_id and copilot.organization_id == org_id:
                if org_role == "org_super_admin":
                    has_access = True
                # Check for explicit 'copilot:use' permission
                elif user_has_permission(main_session, user, "copilot:use"):
                    has_access = True
                else:
                    # Workspace check
                    from app.copilot.models import CopilotWorkspace
                    is_assigned = session.exec(
                        select(CopilotWorkspace).where(
                            CopilotWorkspace.copilot_id == copilot_id,
                            CopilotWorkspace.workspace_id.in_(ws_ids)
                        )
                    ).first()
                    if is_assigned:
                        has_access = True
                    elif org_role == "org_admin" and is_owner: # Redundant if is_owner checked above, but safe
                        has_access = True

        if not has_access:
             # If we haven't found a valid access path yet
             if copilot.visibility != "public":
                 raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        # 2. Inactive/Paused Check
        if copilot.status == "inactive":
            # Only owner or superadmin can use inactive copilots
            if not (is_owner or is_superadmin):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail="This copilot is currently paused. Please contact your organization admin to re-activate it."
                )

        # 3. Draft Check
        elif copilot.status == "draft":
            # ONLY owner or superadmin can chat with a draft
            if not (is_owner or is_superadmin):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail="This copilot is currently in draft and only accessible to the owner for configuration and testing."
                )
        
        # 4. Visibility Checks (Refined)
        # Already handled by has_access + Status checks above.
        # If public, has_access might be False but status is active -> Allowed.
        # If private, has_access MUST be True.
        
        if copilot.visibility != "public" and not has_access:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        # Get or create conversation
        conversation: CopilotConversation
        if message_in.conversation_id:
            conversation = session.get(CopilotConversation, message_in.conversation_id)
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            if conversation.user_id != user.id and not user.is_superuser:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            conversation = CopilotConversation(
                copilot_id=copilot_id,
                user_id=user.id,
                title="New Conversation",
                context=message_in.context,
            )
            session.add(conversation)
            session.commit()
            session.refresh(conversation)

        # Extract workspace context if provided
        workspace_id = message_in.workspace_id
        
        # Fallback to context or legacy field if not provided directly
        if not workspace_id and message_in.context:
            context_ws_id = message_in.context.get("workspaceId") or message_in.context.get("workspace_id")
            if context_ws_id:
                try:
                    workspace_id = uuid.UUID(str(context_ws_id))
                except (ValueError, TypeError):
                    pass

        # Fallback: If no workspace in context, try to infer connection
        if not workspace_id:
            # 1. Check direct workspace assignment for this user
            from app.copilot.models import CopilotWorkspace
            
            # Re-use context fetched earlier if possible, or fetch new
            # We need user's workspaces in this organization
            org_id = copilot.organization_id
            if org_id:
                # Find workspaces in this org where user is a member
                from app.models import WorkspaceMember, Workspace
                
                user_workspaces = main_session.exec(
                    select(Workspace.id).join(WorkspaceMember).where(
                        Workspace.organization_id == org_id,
                        WorkspaceMember.user_id == user.id,
                        WorkspaceMember.status == "active"
                    )
                ).all()
                
                if user_workspaces:
                    # If confirmed assignment exists
                    assigned_ws = session.exec(
                        select(CopilotWorkspace.workspace_id).where(
                            CopilotWorkspace.copilot_id == copilot_id,
                            CopilotWorkspace.workspace_id.in_(user_workspaces)
                        )
                    ).first()
                    
                    if assigned_ws:
                        workspace_id = assigned_ws
                    # If only one workspace exists for user in this org, use it
                    elif len(user_workspaces) == 1:
                        workspace_id = user_workspaces[0]

        try:
            # 1. Get history
            window_size = copilot.memory_window_size if copilot.memory_window_size > 0 else 10
            history_count = window_size * 2 if copilot.memory_enabled else 20
            
            history_statement = (
                select(CopilotMessage)
                .where(CopilotMessage.conversation_id == conversation.id)
                .order_by(CopilotMessage.created_at.desc())
                .limit(history_count)
            )
            history = list(session.exec(history_statement).all())
            history.reverse()

            logger.info(f"[CHAT] Fetched {len(history)} history messages for conversation {conversation.id}")

            # 2. Save user message
            user_message = CopilotMessage(
                conversation_id=conversation.id,
                role="user",
                content=message_in.content,
                attachments=message_in.attachments,
            )
            session.add(user_message)
            session.commit()
            session.refresh(user_message)

            # Build conversation history for agent
            # New: Support multimodal (vision) history by checking for image attachments in previous turns
            conversation_history = []
            
            # Re-verify vision capability for history building
            vision_model_patterns = [
                "gpt-4o", "gpt-4-turbo", "gpt-4-vision", "o1",
                "claude-3-5-sonnet", "claude-3.5-sonnet", "claude-3-5-opus",
                "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
                "gemini-2-0-flash", "gemini-2.0-flash",
                "gemini-1-5-pro", "gemini-1.5-pro",
                "gemini-1-5-flash", "gemini-1.5-flash",
                "gemini-pro-1.5", "gemini-flash-1.5"
            ]
            
            def check_vision_capable_local(m_name: str) -> bool:
                if "/" in m_name:
                    m_name = m_name.split("/")[-1]
                m_norm = m_name.lower().replace(".", "-")
                return any(pattern.replace(".", "-") in m_norm for pattern in vision_model_patterns)

            is_vision_model_enabled = check_vision_capable_local(copilot.model)

            for msg in history:
                msg_content = msg.content
                
                # If this message has image attachments and we're using a vision model, 
                # we should try to reconstruct the multimodal content
                if msg.attachments and msg.role == "user" and is_vision_model_enabled:
                    image_attachments = [a for a in msg.attachments if a.get("type", "").startswith("image/")]
                    if image_attachments:
                        relevant_history_imgs = []
                        for att in image_attachments[:2]: # Limit history images to avoid token blowup
                            try:
                                doc = session.get(CopilotDocument, uuid.UUID(att["id"]))
                                if doc and doc.file_url:
                                    relevant_history_imgs.append({
                                        "type": "image_url",
                                        "image_url": {"url": doc.file_url} 
                                    })
                            except: continue
                        
                        if relevant_history_imgs:
                            msg_content = [{"type": "text", "text": msg.content}] + relevant_history_imgs

                conversation_history.append({
                    "role": msg.role,
                    "content": msg_content
                })



            # Vision Handling - Check if we need to process images
            vision_enabled = "vision" in (copilot.capabilities or [])
            vision_content = []
            has_images = False
            
            vision_model_patterns = [
                "gpt-4o", "gpt-4-turbo", "gpt-4-vision", "o1",
                "claude-3-5-sonnet", "claude-3.5-sonnet", "claude-3-5-opus",
                "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
                "gemini-2-0-flash", "gemini-2.0-flash",
                "gemini-1-5-pro", "gemini-1.5-pro",
                "gemini-1-5-flash", "gemini-1.5-flash",
                "gemini-pro-1.5", "gemini-flash-1.5"
            ]
            
            def check_vision_capable(m_name: str) -> bool:
                if "/" in m_name:
                    m_name = m_name.split("/")[-1]
                m_norm = m_name.lower().replace(".", "-")
                return any(pattern.replace(".", "-") in m_norm for pattern in vision_model_patterns)

            is_vision_model = check_vision_capable(copilot.model)

            # Check for images associated with this conversation (current or very recent)
            recent_image_docs = []
            if vision_enabled:
                # Look for images attached to the current message OR recent messages in this conversation
                # This ensures follow-up questions work
                recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15) # Increased window
                
                # Fetch recent image documents for this copilot/conversation
                img_statement = select(CopilotDocument).where(
                    CopilotDocument.copilot_id == copilot_id,
                    CopilotDocument.created_at >= recent_cutoff,
                    CopilotDocument.file_type.in_(["png", "jpg", "jpeg", "gif", "webp"]),
                    CopilotDocument.file_url != "" 
                ).order_by(CopilotDocument.created_at.desc()).limit(5)
                
                recent_image_docs = session.exec(img_statement).all()

            if recent_image_docs:
                if not vision_enabled:
                    # Vision capability is disabled for this copilot
                    return {
                        "content": "I noticed you uploaded an image, but my Image Understanding (Vision) capability is currently disabled. Please enable it in my settings if you'd like me to analyze images.",
                        "model": copilot.model,
                        "tokens_used": 0,
                        "cost_usd": 0.0,
                    }

                # If we have images but the model isn't vision-capable, attempt to switch to a default vision model
                if not is_vision_model:
                    logger.info(f"[VISION] Switching to vision-capable model for multimodal request")
                    # Temporarily override model for this request
                    # We'll use gpt-4o as the gold standard for vision switching
                    original_model = copilot.model
                    copilot.model = "gpt-4o" 
                    is_vision_model = True

                # Build vision content payload
                vision_content.append({"type": "text", "text": message_in.content})
                for doc in recent_image_docs:
                    try:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            response = await client.get(doc.file_url)
                            response.raise_for_status()
                            image_bytes = response.content
                        base64_image = base64.b64encode(image_bytes).decode('utf-8')
                        mime_types = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
                        mime_type = mime_types.get(doc.file_type.lower(), "image/jpeg")
                        vision_content.append({
                            "type": "image_url", 
                            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                        })
                        has_images = True
                    except Exception as img_error:
                        logger.warning(f"Failed to load image {doc.original_filename}: {img_error}")
                        continue


            # Determine user message content (text or vision)
            user_content = message_in.content
            if has_images and vision_content:
                user_content = vision_content

            # Use autonomous agent system
            from app.services.agent_service import agent_service
            
            start_time = time.time()
            response_time_ms = 0  # Initialize here
            tool_calls_metadata = []  # Store tool calls for response
            
            # Determine if we should use organization billing
            # Rules:
            # 1. Platform Superuser uses personal wallet (or we can decide otherwise, but for now personal)
            # 2. Org Super Admin / Org Admin uses Org Wallet if copilot belongs to org
            # 3. Regular Org Member uses personal wallet even if copilot belongs to org
            use_org_billing = False
            if org_id and copilot.organization_id == org_id:
                if org_role in ["org_super_admin", "org_admin"]:
                    use_org_billing = True
            
            billing_org_id = org_id if use_org_billing else None

            try:
                logger.info(f"[AGENT] Starting autonomous agent execution for copilot {copilot_id}")
                
                # Execute autonomous agent
                agent_result = await agent_service.execute_agent(
                    session=session,
                    main_session=main_session,
                    copilot=copilot,
                    user_id=user.id,
                    user_message=user_content,
                    conversation_history=conversation_history,
                    max_iterations=10,
                    workspace_id=workspace_id,
                    organization_id=billing_org_id,
                    use_copilot_org=use_org_billing
                )

                
                ai_response_content = agent_result["response"]
                tool_calls_made = agent_result.get("tool_calls", 0)
                iterations_used = agent_result.get("iterations", 0)
                agent_steps = agent_result.get("steps", [])
                
                logger.info(f"[AGENT] Completed with {iterations_used} iterations, {tool_calls_made} tool calls")
                
                # Calculate response time
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Estimate tokens (rough approximation based on response length)
                # In production, you'd sum up actual tokens from all agent iterations
                estimated_tokens = int(len(ai_response_content.split()) * 1.3)
                
                # Build tool_calls metadata for response
                for step in agent_steps:
                    if step.get("action") == "tool_call":
                        tool_calls_metadata.append({
                            "tool_name": step.get("tool_name"),
                            "tool_input": step.get("tool_input"),
                            "success": step.get("tool_output", {}).get("success", False)
                        })
                
                # Cost is already deducted by agent service during execution
                ai_result = {
                    "content": ai_response_content,
                    "model": copilot.model,
                    "tokens_used": estimated_tokens,
                    "cost_usd": 0.0,  # Agent service handles credit deduction internally
                }
                
                # Store agent metadata in conversation context for UI display
                if agent_steps:
                    if not conversation.context:
                        conversation.context = {}
                    
                    conversation.context["last_agent_execution"] = {
                        "iterations": iterations_used,
                        "tool_calls": tool_calls_made,
                        "steps": agent_steps[:5], # Store last 5 steps for context
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                
            except Exception as agent_error:
                logger.error(f"[AGENT] Execution failed, falling back to simple response: {agent_error}", exc_info=True)
                
                # Fallback to simple response without agent
                ai_messages = []
                
                # Build system prompt
                system_prompt = copilot.system_prompt or ""
                current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                
                anti_hallucination_rules = f"""
### TEMPORAL CONTEXT:
**Current System Time:** {current_time_str}

### CORE OPERATING INSTRUCTIONS:
1. **Conversation History**: You have full access to the previous messages in this chat. **NEVER** tell the user you don't have memory or that this is a new session if history is provided. Use the context below to maintain a continuous conversation.
2. **Vision & Images**: If images/visual content are provided, describe them accurately and answer questions about them.
3. **Accuracy**: Only provide information you are certain about based on your training data and the conversation history.
4. **Honesty**: If you don't know something, say so clearly. Do not fabricate information.
"""
                system_prompt = system_prompt + anti_hallucination_rules
                
                if system_prompt:
                    ai_messages.append({"role": "system", "content": system_prompt})
                
                # Add conversation history
                ai_messages.extend(conversation_history)
                
                # Add current user message
                ai_messages.append({"role": "user", "content": user_content})
                
                # Generate simple response
                ai_result = await requesty_service.generate_response(
                    messages=ai_messages,
                    model=copilot.model,
                    temperature=copilot.temperature,
                    max_tokens=copilot.max_tokens,
                    session=main_session,
                    user_id=user.id,
                    organization_id=billing_org_id,
                    workspace_id=workspace_id or copilot.workspace_id
                )
                response_time_ms = int((time.time() - start_time) * 1000)



            assistant_message = CopilotMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=ai_result["content"],
                model_used=ai_result.get("model"),
                tokens_used=ai_result.get("tokens_used"),
                cost=Decimal(str(ai_result.get("cost_usd", 0))),
                response_time_ms=response_time_ms,
                tool_calls=tool_calls_metadata if tool_calls_metadata else None,
                agent_steps=agent_steps if agent_steps else None
            )
            session.add(assistant_message)

            conversation.message_count += 2
            conversation.total_tokens_used += ai_result.get("tokens_used", 0)
            conversation.total_cost += Decimal(str(ai_result.get("cost_usd", 0)))
            conversation.last_message_at = datetime.now(timezone.utc)
            conversation.updated_at = datetime.now(timezone.utc)

            if conversation.message_count == 2 and conversation.title == "New Conversation":
                try:
                    new_title = await requesty_service.generate_chat_title(
                        message_in.content,
                        session=main_session,
                        user_id=user.id
                    )
                    conversation.title = new_title
                except Exception:
                    pass

            copilot.usage_count += 1
            session.add(conversation)
            session.add(copilot)
            session.commit()
            session.refresh(assistant_message)

            return SendMessageResponse(
                conversation_id=conversation.id,
                user_id=conversation.user_id,
                message_id=user_message.id,
                response_id=assistant_message.id,
                content=assistant_message.content,
                tool_calls=assistant_message.tool_calls,
                model_used=assistant_message.model_used or copilot.model,
                tokens_used=assistant_message.tokens_used or 0,
                cost=assistant_message.cost or Decimal("0"),
                response_time_ms=response_time_ms,
                agent_steps=assistant_message.agent_steps,
                created_at=assistant_message.created_at,
            )
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            logger.error(f"Failed to generate response: {e}", exc_info=True)
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to generate response: {str(e)}")

copilot_chat_service = CopilotChatService()
