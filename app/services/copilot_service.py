
import logging
import uuid
import json
import time
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select, func, col, or_

from app.core.config import settings
from app.models import User, Role, UserRole
from app.api.deps import CurrentUser
from app.copilot.models import (
    Copilot, CopilotShare, CopilotConversation, CopilotMessage, CopilotDocument, CopilotDocumentChunk
)
from app.copilot.schemas import (
    CopilotCreate, CopilotUpdate, CopilotPublic, CopilotsPublic,
    ShareCopilotRequest, CopilotSuggestionsResponse
)
from app.services.email_service import email_service
from app.services.requesty_ai import requesty_service
from app.utils.permissions import user_has_permission

logger = logging.getLogger(__name__)

class CopilotService:
    async def create_copilot(
        self, 
        session: Session, 
        main_session: Session, 
        user: CurrentUser, 
        copilot_in: CopilotCreate
    ) -> CopilotPublic:
        """Create a new copilot."""
        # Get Organization Context
        from app.models import OrganizationMember
        org_member = main_session.exec(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        ).first()
        organization_id = org_member.organization_id if org_member else None

        copilot = Copilot(
            name=copilot_in.name,
            description=copilot_in.description,
            category=copilot_in.category,
            visibility=copilot_in.visibility,
            model=copilot_in.model,
            system_prompt=copilot_in.system_prompt,
            welcome_message=copilot_in.welcome_message,
            suggested_prompts=copilot_in.suggested_prompts,
            capabilities=copilot_in.capabilities,
            temperature=copilot_in.temperature,
            max_tokens=copilot_in.max_tokens,
            tags=copilot_in.tags,
            created_by=user.id,
            organization_id=organization_id,
            is_featured=copilot_in.is_featured if user.is_superuser else False,
            is_official=copilot_in.is_official if user.is_superuser else False,
        )
        session.add(copilot)
        session.commit()
        session.refresh(copilot)

        # Assignment to workspaces is now a separate, manual step performed by administrators.
        # We no longer automatically create a CopilotWorkspace entry during creation.

        # We can construct the response directly or via populate helper
        # Since it's just created, we know the creator is the current user.
        res = CopilotPublic.model_validate(copilot)
        res.created_by_name = user.full_name or (user.email.split('@')[0] if user.email else "User")
        res.created_by_username = user.tag_number or user.username or (user.email.split('@')[0] if user.email else "user")
        res.assigned_workspaces_ids = []
        
        return res

    async def _get_user_context(self, main_session: Session, user: CurrentUser):
        """Helper to get user's organization and workspaces."""
        from app.models import OrganizationMember, WorkspaceMember
        
        org_member = main_session.exec(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        ).first()
        
        if not org_member:
            return None, "member", []
            
        org_id = org_member.organization_id
        org_role = org_member.role
        
        ws_ids = main_session.exec(
            select(WorkspaceMember.workspace_id).where(
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.status == "active"
            )
        ).all()
        
        return org_id, org_role, list(ws_ids)

    async def list_accessible_copilots(
        self,
        session: Session,
        main_session: Session,
        user: CurrentUser,
        skip: int = 0,
        limit: int = 50,
        filters: Dict[str, Any] = {}
    ) -> CopilotsPublic:
        """
        List copilots accessible to the user based on role and organization.
        """
        org_id, org_role, ws_ids = await self._get_user_context(main_session, user)
        
        from app.copilot.models import CopilotWorkspace
        
        # Superusers bypass all visibility rules
        if user.is_superuser:
            statement = select(Copilot)
        else:
            # Base conditions: Always allow public, featured, or owned by user
            conditions = [
                Copilot.visibility == "public",
                Copilot.is_featured == True,
                Copilot.created_by == user.id
            ]

            # Workspace visibility within organization
            if org_id:
                conditions.append(
                    (Copilot.visibility == "workspace") & (Copilot.organization_id == org_id)
                )
            
            # Shared explicitly with user
            conditions.append(
                Copilot.id.in_(
                    select(CopilotShare.copilot_id).where(
                        or_(CopilotShare.user_id == user.id, CopilotShare.email == user.email)
                    )
                )
            )

            if org_id:
                if org_role == "org_super_admin":
                    # Super Admin sees ALL organization copilots
                    conditions.append(Copilot.organization_id == org_id)
                else:
                    # Admin & Members: See what's assigned to THEIR workspaces
                    if ws_ids:
                        ws_copilot_ids = session.exec(
                            select(CopilotWorkspace.copilot_id).where(CopilotWorkspace.workspace_id.in_(ws_ids))
                        ).all()
                        if ws_copilot_ids:
                            conditions.append(Copilot.id.in_(list(ws_copilot_ids)))
                    
                    # Org Admins also see copilots they created within the organization
                    if org_role == "org_admin":
                        conditions.append((Copilot.organization_id == org_id) & (Copilot.created_by == user.id))

            statement = select(Copilot).where(or_(*conditions))

            # Filter out drafts for regular users (non-owners, non-superadmins)
            if not user.is_superuser:
                statement = statement.where(
                    or_(
                        Copilot.status != "draft",
                        Copilot.created_by == user.id
                    )
                )

        logger.info(f"Listing accessible copilots for user {user.id}. Org: {org_id}, Role: {org_role}")

        # Filters
        if filters.get("category"):
            statement = statement.where(Copilot.category == filters["category"])
        if filters.get("visibility"):
            statement = statement.where(Copilot.visibility == filters["visibility"])
        if filters.get("is_featured") is not None:
            statement = statement.where(Copilot.is_featured == filters["is_featured"])
        if filters.get("search"):
            search_filter = f"%{filters['search'].lower()}%"
            statement = statement.where(
                or_(
                    func.lower(Copilot.name).like(search_filter),
                    func.lower(Copilot.description).like(search_filter),
                )
            )

        # Count
        count_statement = select(func.count()).select_from(statement.subquery())
        total = session.exec(count_statement).one()

        # Pagination
        statement = statement.order_by(col(Copilot.created_at).desc()).offset(skip).limit(limit)
        copilots = session.exec(statement).all()

        copilots_public = await self._populate_user_names(copilots, main_session, session)
        return CopilotsPublic(copilots=copilots_public, total=total)

    async def list_all_copilots_admin(
        self,
        session: Session,
        main_session: Session,
        skip: int = 0,
        limit: int = 50,
        filters: Dict[str, Any] = {}
    ) -> CopilotsPublic:
        """
        List ALL copilots (Admin only).
        """
        logger.info(f"Admin listing all copilots. Filters: {filters}")
        statement = select(Copilot)

        # Filters
        if filters.get("category"):
            statement = statement.where(Copilot.category == filters["category"])
        if filters.get("visibility"):
            statement = statement.where(Copilot.visibility == filters["visibility"])
        if filters.get("is_featured") is not None:
            statement = statement.where(Copilot.is_featured == filters["is_featured"])
        if filters.get("workspace_id"):
             statement = statement.where(Copilot.workspace_id == filters["workspace_id"])
        if filters.get("status"):
            statement = statement.where(Copilot.status == filters["status"])
        
        if filters.get("search"):
            search_filter = f"%{filters['search'].lower()}%"
            statement = statement.where(
                or_(
                    func.lower(Copilot.name).like(search_filter),
                    func.lower(Copilot.description).like(search_filter),
                )
            )

        # Count
        count_statement = select(func.count()).select_from(statement.subquery())
        total = session.exec(count_statement).one()

        # Pagination
        statement = statement.order_by(col(Copilot.created_at).desc()).offset(skip).limit(limit)
        copilots = session.exec(statement).all()

        copilots_public = await self._populate_user_names(copilots, main_session, session)
        return CopilotsPublic(copilots=copilots_public, total=total)

    async def list_featured_copilots(
        self,
        session: Session,
        main_session: Session,
        skip: int = 0,
        limit: int = 20
    ) -> CopilotsPublic:
        """List featured/official public copilots."""
        # Get all platform-level admin roles
        admin_roles = ["platform_super_admin", "platform_admin", "ai_copilot_admin"]
        role_stmt = select(Role.id).where(Role.name.in_(admin_roles))
        admin_role_ids = main_session.exec(role_stmt).all()
        
        # Get all users with these roles OR with is_superuser flag
        super_admin_ids = set()
        
        # 1. Users with roles
        if admin_role_ids:
            user_role_stmt = select(UserRole.user_id).where(UserRole.role_id.in_(admin_role_ids))
            ids_from_roles = main_session.exec(user_role_stmt).all()
            super_admin_ids.update(ids_from_roles)
            
        # 2. Users with is_superuser flag (fallback)
        superuser_stmt = select(User.id).where(User.is_superuser == True)
        ids_from_flag = main_session.exec(superuser_stmt).all()
        super_admin_ids.update(ids_from_flag)

        featured_conditions = [
            Copilot.is_featured == True,
            Copilot.is_official == True
        ]
        
        if super_admin_ids:
            featured_conditions.append(Copilot.created_by.in_(list(super_admin_ids)))

        statement = (
            select(Copilot)
            .where(
                Copilot.visibility == "public",
                or_(*featured_conditions),
            )
            .order_by(col(Copilot.usage_count).desc())
            .offset(skip)
            .limit(limit)
        )
        copilots = session.exec(statement).all()

        # Force official status for prebuilt templates logic from original code
        for c in copilots:
            c.is_official = True

        count_statement = select(func.count()).select_from(Copilot).where(
            Copilot.visibility == "public",
            or_(*featured_conditions),
        )
        total = session.exec(count_statement).one()

        copilots_public = await self._populate_user_names(copilots, main_session, session)
        for cp in copilots_public:
            cp.is_official = True
            
        return CopilotsPublic(copilots=copilots_public, total=total)

    async def list_my_copilots(
        self,
        session: Session,
        main_session: Session,
        user: CurrentUser,
        skip: int = 0,
        limit: int = 50
    ) -> CopilotsPublic:
        """List user's own copilots or assigned copilots for members."""
        org_id, org_role, ws_ids = await self._get_user_context(main_session, user)
        
        if org_role in ["org_super_admin", "org_admin"]:
            # Admin: copilots they created
            condition = Copilot.created_by == user.id
        else:
            # Member: copilots assigned to their workspace(s)
            from app.copilot.models import CopilotWorkspace
            if not ws_ids:
                return CopilotsPublic(copilots=[], total=0)
            
            ws_copilot_ids = session.exec(
                select(CopilotWorkspace.copilot_id).where(CopilotWorkspace.workspace_id.in_(ws_ids))
            ).all()
            
            if not ws_copilot_ids:
                return CopilotsPublic(copilots=[], total=0)
                
            condition = Copilot.id.in_(list(ws_copilot_ids))

        statement = (
            select(Copilot)
            .where(condition)
            .order_by(col(Copilot.updated_at).desc())
            .offset(skip)
            .limit(limit)
        )
        copilots = session.exec(statement).all()

        count_statement = select(func.count()).select_from(Copilot).where(condition)
        total = session.exec(count_statement).one()

        copilots_public = await self._populate_user_names(copilots, main_session, session)
        return CopilotsPublic(copilots=copilots_public, total=total)

    async def get_copilot(
        self,
        session: Session,
        main_session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser
    ) -> CopilotPublic:
        """Get a single copilot, enforcing permissions."""
        copilot = session.get(Copilot, copilot_id)

        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")

        is_owner = copilot.created_by == user.id
        is_public = copilot.visibility == "public"
        
        if not is_owner and not is_public and not user.is_superuser:
            # Check organization level access
            org_id, org_role, ws_ids = await self._get_user_context(main_session, user)
            
            # 1. Share check
            share = session.exec(
                select(CopilotShare).where(
                    CopilotShare.copilot_id == copilot_id,
                    or_(CopilotShare.user_id == user.id, CopilotShare.email == user.email)
                )
            ).first()
            if share:
                res = await self._populate_user_names([copilot], main_session, session)
                return res[0]
            
            # 2. Org check
            if org_id and copilot.organization_id == org_id:
                if org_role == "org_super_admin" or user_has_permission(main_session, user, "copilot:use"):
                     # Super Admin or users with explicit use permission see everything in org
                     pass
                else:
                    # Admin & Members: Only if assigned to their workspaces
                    from app.copilot.models import CopilotWorkspace
                    is_assigned = session.exec(
                        select(CopilotWorkspace).where(
                            CopilotWorkspace.copilot_id == copilot_id,
                            CopilotWorkspace.workspace_id.in_(ws_ids)
                        )
                    ).first()
                    
                    if not is_assigned:
                        raise HTTPException(status_code=403, detail="Access denied. Workspace membership or 'copilot:use' permission required.")
            else:
                # Not public, not owned, not in org, not shared
                raise HTTPException(status_code=403, detail="Access denied")

        copilots_public = await self._populate_user_names([copilot], main_session, session)
        return copilots_public[0]

    async def update_copilot(
        self,
        session: Session,
        main_session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser,
        copilot_in: CopilotUpdate
    ) -> CopilotPublic:
        """Update copilot."""
        copilot = session.get(Copilot, copilot_id)
        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")

        if copilot.created_by != user.id and not user.is_superuser:
            # Replicate org admin check from delete_copilot
            org_id, org_role, _ = await self._get_user_context(main_session, user)
            is_org_admin = (org_id is not None and 
                            copilot.organization_id == org_id and 
                            org_role in ["org_super_admin", "org_admin"])
                            
            if not is_org_admin:
                raise HTTPException(status_code=403, detail="Only the owner or an admin can update this copilot")

        update_data = copilot_in.model_dump(exclude_unset=True)
        
        # Restrict administrative flags to superusers only
        if not user.is_superuser:
            removed_flags = []
            if "is_official" in update_data:
                update_data.pop("is_official")
                removed_flags.append("is_official")
            if "is_featured" in update_data:
                update_data.pop("is_featured")
                removed_flags.append("is_featured")
            if removed_flags:
                logger.info(f"User {user.id} attempted to change administrative flags {removed_flags} without superuser permissions")

        for field, value in update_data.items():
            setattr(copilot, field, value)

        copilot.updated_at = datetime.now(timezone.utc)
        session.add(copilot)
        session.commit()
        session.refresh(copilot)

        # Log activity
        try:
            from app.services.copilot_analytics_service import copilot_analytics_service
            await copilot_analytics_service.log_activity(
                session=session,
                copilot_id=copilot_id,
                user_id=user.id,
                activity_type="settings_applied",
                title="Settings Applied",
                description="Configuration settings updated successfully",
                source="UPDATED VIA MANAGEMENT CENTER",
                status="success",
                metadata={"fields_updated": list(update_data.keys())}
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")

        copilots_public = await self._populate_user_names([copilot], main_session, session)
        return copilots_public[0]


    async def update_status(
        self,
        session: Session,
        main_session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser,
        new_status: str
    ) -> CopilotPublic:
        """Update copilot status with transition validation."""
        copilot = session.get(Copilot, copilot_id)
        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")

        # Permissions: Owner, Org Admin, or Platform Superuser
        is_owner = copilot.created_by == user.id
        is_superuser = user.is_superuser
        
        org_id, org_role, _ = await self._get_user_context(main_session, user)
        is_org_admin = (org_id is not None and 
                        copilot.organization_id == org_id and 
                        org_role in ["org_super_admin", "org_admin"])

        if not (is_owner or is_superuser or is_org_admin):
            raise HTTPException(
                status_code=403, 
                detail="Access Denied. Only admins can delete or disable this copilot"
            )

        # Validation: prevent setting to invalid status
        allowed_statuses = ["active", "inactive", "disabled", "draft"]
        if new_status not in allowed_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

        # Business Logic: Transition Validation
        # Example: If a platform admin disabled it, maybe owner cannot re-activate?
        # But per requirements: "organization admin ... should be able to have control"
        
        copilot.status = new_status
        copilot.updated_at = datetime.now(timezone.utc)
        
        session.add(copilot)
        session.commit()
        session.refresh(copilot)

        copilots_public = await self._populate_user_names([copilot], main_session, session)
        return copilots_public[0]

    async def delete_copilot(
        self,
        session: Session,
        main_session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser
    ) -> None:
        """Delete copilot."""
        copilot = session.get(Copilot, copilot_id)
        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")
            
        # Permissions: Owner, Org Admin, or Platform Superuser
        is_owner = copilot.created_by == user.id
        is_superuser = user.is_superuser
        
        org_id, org_role, _ = await self._get_user_context(main_session, user)
        is_org_admin = (org_id is not None and 
                        copilot.organization_id == org_id and 
                        org_role in ["org_super_admin", "org_admin"])

        if not (is_owner or is_superuser or is_org_admin):
            raise HTTPException(
                status_code=403, 
                detail="Access Denied. Only admins can delete or disable this copilot"
            )

        session.delete(copilot)
        session.commit()

    async def duplicate_copilot(
        self,
        session: Session,
        main_session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser
    ) -> CopilotPublic:
        """Duplicate an existing copilot."""
        original_copilot = session.get(Copilot, copilot_id)
        
        if not original_copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")
        
        if original_copilot.visibility == "private" and original_copilot.created_by != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Access denied")
        
        duplicate = Copilot(
            name=f"{original_copilot.name} (Copy)",
            description=original_copilot.description,
            category=original_copilot.category,
            visibility="private",
            model=original_copilot.model,
            system_prompt=original_copilot.system_prompt,
            welcome_message=original_copilot.welcome_message,
            suggested_prompts=original_copilot.suggested_prompts,
            capabilities=original_copilot.capabilities,
            temperature=original_copilot.temperature,
            max_tokens=original_copilot.max_tokens,
            top_p=original_copilot.top_p,
            frequency_penalty=original_copilot.frequency_penalty,
            presence_penalty=original_copilot.presence_penalty,
            stop_sequences=original_copilot.stop_sequences,
            tags=original_copilot.tags,
            created_by=user.id,
            allow_file_uploads=original_copilot.allow_file_uploads,
            allow_web_search=original_copilot.allow_web_search,
            allow_code_execution=original_copilot.allow_code_execution,
            memory_enabled=original_copilot.memory_enabled,
            memory_window_size=original_copilot.memory_window_size,
        )
        
        session.add(duplicate)
        session.commit()
        session.refresh(duplicate)
        
        copilots_public = await self._populate_user_names([duplicate], main_session, session)
        return copilots_public[0]

    async def share_copilot(
        self,
        session: Session,
        main_session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser,
        share_request: ShareCopilotRequest
    ) -> dict:
        """Share copilot via email."""
        copilot = session.get(Copilot, copilot_id)
        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")
        
        if copilot.created_by != user.id and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Only the owner or an admin can share this copilot")
        
        invitations_sent = 0
        for email in share_request.emails:
            email = email.lower().strip()
            if not email:
                continue
                
            # Check existing share
            existing_share = session.exec(
                select(CopilotShare).where(
                    CopilotShare.copilot_id == copilot_id,
                    CopilotShare.email == email
                )
            ).first()
            
            if existing_share:
                logger.info(f"Copilot already shared with {email}, skipping")
                continue
                
            # Find user in main DB
            target_user = main_session.exec(select(User).where(User.email == email)).first()
            target_user_id = target_user.id if target_user else None
            
            # Create share
            share = CopilotShare(
                copilot_id=copilot_id,
                user_id=target_user_id,
                email=email,
                message=share_request.message,
                shared_by=user.id,
            )
            session.add(share)
            invitations_sent += 1
            
            # Send Notification
            try:
                email_service.send_workspace_notification(
                    email_to=email,
                    username=target_user.full_name if target_user else email.split('@')[0],
                    workspace_name="Qorebit",
                    notification_title=f"Copilot Shared: {copilot.name}",
                    notification_message=f"{user.full_name or user.email} shared a copilot with you: \"{copilot.name}\"." + 
                                         (f"\n\nMessage: {share_request.message}" if share_request.message else ""),
                    action_link=f"{settings.FRONTEND_HOST}/copilot-hub?id={copilot.id}"
                )
            except Exception as e:
                logger.error(f"Failed to send share email to {email}: {e}")

        session.commit()
        return {
            "status": "success",
            "message": f"Copilot shared with {invitations_sent} new user(s)",
            "emails": share_request.emails,
        }

    async def generate_suggestions(
        self,
        session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser
    ) -> CopilotSuggestionsResponse:
        """Generate dynamic suggestions using RequestyAI."""
        # Note: Implementing the simpler caching here for now, could be redis later
        # We'll attach the cache to the instance or global. 
        # Since this service might be instantiated or singleton, let's use a class level or module level cache?
        # The original code attached it to the function. 
        # I'll use a simple dict on the class for now, mindful of scope.
        
        if not hasattr(self, "_suggestions_cache"):
            self._suggestions_cache = {}

        cache_key = f"{copilot_id}:{user.id}"
        now = time.time()
        
        if cache_key in self._suggestions_cache:
            cached_data, timestamp = self._suggestions_cache[cache_key]
            if now - timestamp < 300:
                return CopilotSuggestionsResponse(**cached_data)

        copilot = session.get(Copilot, copilot_id)
        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")

        # Gather Context
        context = {
            "name": copilot.name,
            "description": copilot.description,
            "instructions": copilot.system_prompt[:2000] if copilot.system_prompt else "",
            "documents": [],
            "recent_topics": []
        }

        # Documents
        docs = session.exec(select(CopilotDocument).where(CopilotDocument.copilot_id == copilot_id, CopilotDocument.status == 'completed').limit(5)).all()
        doc_ids = [d.id for d in docs]
        
        for d in docs:
            context["documents"].append({"title": d.title, "description": d.description})

        if doc_ids:
            chunks = session.exec(select(CopilotDocumentChunk).where(CopilotDocumentChunk.document_id.in_(doc_ids), CopilotDocumentChunk.chunk_index == 0).limit(5)).all()
            for c in chunks:
                doc_title = next((d.title for d in docs if d.id == c.document_id), "Unknown")
                context["documents"].append({"source": doc_title, "teaser": c.content[:300]})

        # History
        last_conv = session.exec(
            select(CopilotConversation)
            .where(CopilotConversation.copilot_id == copilot_id, CopilotConversation.user_id == user.id)
            .order_by(col(CopilotConversation.updated_at).desc())
            .limit(1)
        ).first()

        if last_conv:
            messages = session.exec(
                select(CopilotMessage)
                .where(CopilotMessage.conversation_id == last_conv.id)
                .order_by(col(CopilotMessage.created_at).desc())
                .limit(6)
            ).all()
            for m in reversed(messages):
                if m.role == "user":
                    context["recent_topics"].append(m.content[:200])

        # Prompt
        ai_system_prompt = """You are an expert AI prompt engineer. 
Your task is to generate 4 highly relevant, diverse, and useful conversation starters (suggested prompts) for a specific AI Copilot.

RULES:
1. Prompts should be concise (max 15 words each).
2. Prompts should reflect the Copilot's personality and the documents it has access to.
3. If there is recent conversation history, generate follow-up questions or related topics.
4. Output MUST be a valid JSON list of strings.
5. Do not include introductory text, skip explanations.

Example Output:
["Summarize the main findings", "How does this impact workers?", "Key recommendations?", "Who are the authors?"]
"""
        ai_user_prompt = f"COPILOT CONTEXT:\n{json.dumps(context, indent=2)}\n\nGenerate 4 suggestions in JSON format."

        try:
            response = await requesty_service.generate_response(
                messages=[
                    {"role": "system", "content": ai_system_prompt},
                    {"role": "user", "content": ai_user_prompt}
                ],
                model="openai/gpt-4o-mini",
                temperature=0.8
            )
            
            content = response["content"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            suggestions = json.loads(content)
            if not isinstance(suggestions, list):
                suggestions = []
                
            result = {"suggestions": suggestions[:5], "source": "dynamic"}
            self._suggestions_cache[cache_key] = (result, now)
            return CopilotSuggestionsResponse(**result)
            
        except Exception as e:
            logger.error(f"Failed to generate dynamic suggestions: {e}")
            man_suggestions = copilot.suggested_prompts or []
            return CopilotSuggestionsResponse(suggestions=man_suggestions[:5], source="manual")

    async def _populate_user_names(self, copilots: List[Copilot], main_session: Session, copilot_session: Session) -> List[CopilotPublic]:
        if not copilots:
            return []
        
        user_ids = {c.created_by for c in copilots}
        users_statement = select(User).where(User.id.in_(list(user_ids)))
        users = main_session.exec(users_statement).all()
        
        user_name_map = {str(u.id): u.full_name or (u.email.split('@')[0] if u.email else "User") for u in users}
        user_tag_map = {str(u.id): u.tag_number or u.username or (u.email.split('@')[0] if u.email else "user") for u in users}
        
        # Populate Workspaces
        from app.copilot.models import CopilotWorkspace
        ids = [c.id for c in copilots]
        ws_stmt = select(CopilotWorkspace).where(CopilotWorkspace.copilot_id.in_(ids))
        all_ws = copilot_session.exec(ws_stmt).all()
        
        ws_map = {}
        for cw in all_ws:
            if str(cw.copilot_id) not in ws_map:
                ws_map[str(cw.copilot_id)] = []
            ws_map[str(cw.copilot_id)].append(cw.workspace_id)

        result = []
        for c in copilots:
            c_public = CopilotPublic.model_validate(c)
            user_id_str = str(c.created_by)
            c_public.created_by_name = user_name_map.get(user_id_str) or ("Qorebit Team" if c.is_official else "Qorebit User")
            c_public.created_by_username = user_tag_map.get(user_id_str) or ("qorebit" if c.is_official else "user")
            c_public.assigned_workspaces_ids = ws_map.get(str(c.id), [])
            result.append(c_public)
        return result

    async def assign_to_workspaces(
        self,
        session: Session,
        main_session: Session,
        copilot_id: uuid.UUID,
        user: CurrentUser,
        workspace_ids: List[uuid.UUID]
    ) -> CopilotPublic:
        """Assign/Sync copilot to multiple workspaces."""
        copilot = session.get(Copilot, copilot_id)
        if not copilot:
            raise HTTPException(status_code=404, detail="Copilot not found")

        # Permission logic from todo.md:
        # org_admin: Can assign only to workspaces they are members of
        # org_super_admin: Can assign to all workspaces in org
        # org_member: Cannot open modal (enforced in API here by roles)
        
        org_id, org_role, user_ws_ids = await self._get_user_context(main_session, user)
        
        logger.info(f"Assigning copilot {copilot_id} to workspaces {workspace_ids}. User: {user.id}, Org: {org_id}, Role: {org_role}")
        
        # Superusers bypass checks
        is_admin = user.is_superuser or org_role in ["org_super_admin", "org_admin"]
        
        if not is_admin:
             logger.warning(f"User {user.id} is not an admin. Role: {org_role}")
             raise HTTPException(status_code=403, detail="Only organization admins can assign copilots.")

        # Ensure copilot belongs to user's organization or claim it if orphan
        if copilot.organization_id:
            if copilot.organization_id != org_id and not user.is_superuser:
                 logger.warning(f"Mismatched Org. Copilot Org: {copilot.organization_id}, User Org: {org_id}")
                 raise HTTPException(status_code=403, detail="Copilot does not belong to your organization.")
        else:
            # Adoptorphan copilot if current user is the creator or an admin in an org
            if (copilot.created_by == user.id or is_admin) and org_id:
                logger.info(f"Adopting orphan copilot {copilot_id} for org {org_id}")
                copilot.organization_id = org_id
                session.add(copilot)
                session.commit()
                session.refresh(copilot)

        # Filter workspace_ids based on role
        valid_ws_ids = []
        if org_role == "org_super_admin" or user.is_superuser:
            # Check if workspaces belong to the org
            from app.models import Workspace
            ws_stmt = select(Workspace.id).where(Workspace.organization_id == org_id)
            org_ws_ids = main_session.exec(ws_stmt).all()
            valid_ws_ids = [wid for wid in workspace_ids if wid in org_ws_ids]
        else:
            # org_admin: only those they are part of
            valid_ws_ids = [wid for wid in workspace_ids if wid in user_ws_ids]
        
        # Sync CopilotWorkspace entries
        from app.copilot.models import CopilotWorkspace
        # Delete existing
        from sqlmodel import delete
        session.exec(delete(CopilotWorkspace).where(CopilotWorkspace.copilot_id == copilot_id))
        
        # Add new ones
        for wid in valid_ws_ids:
            session.add(CopilotWorkspace(copilot_id=copilot_id, workspace_id=wid))
        
        session.commit()
        session.refresh(copilot)
        
        return (await self._populate_user_names([copilot], main_session, session))[0]

copilot_service = CopilotService()

