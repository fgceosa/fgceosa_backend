"""
Google Drive API Routes
Handles OAuth authentication and file operations with Google Drive
"""
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep, CopilotSessionDep
from app.models import OAuthConnection
from app.services.google_drive_service import google_drive_service
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google-drive", tags=["Google Drive"])



# ==================== Schemas ====================

class GoogleDriveAuthURL(BaseModel):
    """Response with Google Drive OAuth authorization URL"""
    authorization_url: str = Field(alias="authorizationUrl")
    state: str

    model_config = {"populate_by_name": True, "by_alias": True}


class GoogleDriveCallback(BaseModel):
    """Request body for OAuth callback"""
    code: str
    state: str


class GoogleDriveConnectionPublic(BaseModel):
    """Public representation of Google Drive connection"""
    id: str
    provider_email: str | None = Field(default=None, alias="providerEmail")
    is_active: bool = Field(default=False, alias="isActive")
    last_synced_at: datetime | None = Field(default=None, alias="lastSyncedAt")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True, "by_alias": True}


class GoogleDriveFile(BaseModel):
    """Google Drive file metadata"""
    id: str
    name: str
    # Accept both snake_case (from service) and camelCase (for frontend)
    mime_type: str = Field(default="", alias="mimeType")
    size: int = Field(default=0)
    modified_time: str | None = Field(default=None, alias="modifiedTime")
    icon_url: str | None = Field(default=None, alias="iconUrl")
    web_view_link: str | None = Field(default=None, alias="webViewLink")
    is_folder: bool = Field(default=False, alias="isFolder")
    is_supported: bool = Field(default=False, alias="isSupported")
    can_import: bool = Field(default=False, alias="canImport")

    model_config = {
        "populate_by_name": True,  # Accept both snake_case and alias names
        "by_alias": True,  # Serialize using alias names
    }


class GoogleDriveFilesList(BaseModel):
    """List of Google Drive files"""
    files: list[GoogleDriveFile] = Field(default_factory=list)
    next_page_token: str | None = Field(default=None, alias="nextPageToken")

    model_config = {
        "populate_by_name": True,
        "by_alias": True,
    }


class ImportFileRequest(BaseModel):
    """Request to import file from Google Drive"""
    file_id: str = Field(alias="fileId")
    copilot_id: uuid.UUID = Field(alias="copilotId")

    model_config = {"populate_by_name": True}



# ==================== Helper Functions ====================

async def get_active_connection(session: Session, user_id: uuid.UUID) -> OAuthConnection:
    """Get active Google Drive connection for user"""
    statement = select(OAuthConnection).where(
        OAuthConnection.user_id == user_id,
        OAuthConnection.provider == "google-drive",
        OAuthConnection.is_active == True
    )
    connection = session.exec(statement).first()

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="No active Google Drive connection found. Please connect your Google Drive account first."
        )

    # Check if token needs refresh
    if connection.expires_at:
        # Handle timezone-naive datetimes from database by treating them as UTC
        expires_at = connection.expires_at
        if expires_at.tzinfo is None:
            # Make it timezone-aware by assuming it's UTC
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        now_utc = datetime.now(timezone.utc)
        
        if expires_at <= now_utc:
            if not connection.refresh_token:
                raise HTTPException(
                    status_code=401,
                    detail="Google Drive connection expired. Please reconnect your account."
                )

            # Refresh token
            try:
                logger.info(f"[GDRIVE] Token expired for user {user_id}, refreshing...")
                token_data = await google_drive_service.refresh_access_token(connection.refresh_token)

                connection.access_token = token_data['access_token']
                connection.expires_at = token_data['expires_at']
                connection.updated_at = datetime.now(timezone.utc)
                session.add(connection)
                session.commit()
                session.refresh(connection)
                logger.info(f"[GDRIVE] Token refreshed successfully for user {user_id}")
            except Exception as e:
                logger.error(f"[GDRIVE] Token refresh failed for user {user_id}: {str(e)}")
                raise HTTPException(
                    status_code=401,
                    detail=f"Failed to refresh Google Drive token: {str(e)}"
                )

    return connection



# ==================== Routes ====================

@router.get("/auth/url", response_model=GoogleDriveAuthURL)
async def get_google_drive_auth_url(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get Google Drive OAuth authorization URL.

    Returns URL for user to authorize Google Drive access.
    """
    from app.core.config import settings

    # Validate Google credentials are configured
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration is not configured. Please contact your administrator to set up Google OAuth credentials."
        )

    # Check if credentials look valid
    if not settings.GOOGLE_CLIENT_ID.endswith('.apps.googleusercontent.com'):
        raise HTTPException(
            status_code=503,
            detail="Invalid Google OAuth configuration. Please check GOOGLE_CLIENT_ID in server settings."
        )

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state in session or cache (for production, use Redis)
    # For now, we'll just return it and validate in callback

    try:
        authorization_url = google_drive_service.get_authorization_url(state)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate Google OAuth URL: {str(e)}"
        )

    response = GoogleDriveAuthURL(
        authorization_url=authorization_url,
        state=state
    )
    return response.model_dump(by_alias=True)


@router.post("/auth/callback")
async def google_drive_auth_callback(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    callback_data: GoogleDriveCallback,
) -> Any:
    """
    Handle Google Drive OAuth callback.

    Exchange authorization code for access/refresh tokens and store connection.
    """
    try:
        # Exchange code for tokens (now async)
        token_data = await google_drive_service.exchange_code_for_tokens(
            code=callback_data.code,
            state=callback_data.state
        )


        # Check if connection already exists
        statement = select(OAuthConnection).where(
            OAuthConnection.user_id == current_user.id,
            OAuthConnection.provider == "google-drive",
            OAuthConnection.provider_user_id == token_data['user_id']
        )
        existing_connection = session.exec(statement).first()

        if existing_connection:
            # Update existing connection
            existing_connection.access_token = token_data['access_token']
            existing_connection.refresh_token = token_data['refresh_token']
            existing_connection.expires_at = token_data['expires_at']
            existing_connection.scopes = str(token_data['scopes'])
            existing_connection.is_active = True
            existing_connection.updated_at = datetime.now(timezone.utc)
            session.add(existing_connection)
            connection = existing_connection
        else:
            # Create new connection
            connection = OAuthConnection(
                user_id=current_user.id,
                provider="google-drive",
                provider_user_id=token_data['user_id'],
                provider_email=token_data['user_email'],
                access_token=token_data['access_token'],
                refresh_token=token_data['refresh_token'],
                expires_at=token_data['expires_at'],
                scopes=str(token_data['scopes']),
                connection_metadata={'user_name': token_data.get('user_name')},
            )
            session.add(connection)

        session.commit()
        session.refresh(connection)

        connection_data = GoogleDriveConnectionPublic(
            id=str(connection.id),
            provider_email=connection.provider_email,
            is_active=connection.is_active,
            last_synced_at=connection.last_synced_at,
            created_at=connection.created_at,
        ).model_dump(by_alias=True)

        return {
            "message": "Google Drive connected successfully",
            "connection": connection_data
        }

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to connect Google Drive: {str(e)}"
        )


@router.get("/connection", response_model=GoogleDriveConnectionPublic | None)
async def get_google_drive_connection(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get current user's Google Drive connection status.
    """
    statement = select(OAuthConnection).where(
        OAuthConnection.user_id == current_user.id,
        OAuthConnection.provider == "google-drive",
        OAuthConnection.is_active == True
    )
    connection = session.exec(statement).first()

    if not connection:
        return None

    return GoogleDriveConnectionPublic(
        id=str(connection.id),
        provider_email=connection.provider_email,
        is_active=connection.is_active,
        last_synced_at=connection.last_synced_at,
        created_at=connection.created_at,
    ).model_dump(by_alias=True)


@router.delete("/connection")
async def disconnect_google_drive(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Disconnect Google Drive account.
    """
    statement = select(OAuthConnection).where(
        OAuthConnection.user_id == current_user.id,
        OAuthConnection.provider == "google-drive",
        OAuthConnection.is_active == True
    )
    connection = session.exec(statement).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No active Google Drive connection found")

    connection.is_active = False
    connection.updated_at = datetime.now(timezone.utc)
    session.add(connection)
    session.commit()

    return {"message": "Google Drive disconnected successfully"}


@router.get("/files", response_model=GoogleDriveFilesList)
async def list_google_drive_files(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    folder_id: str | None = Query(None, description="Folder ID to list files from"),
    page_token: str | None = Query(None, description="Page token for pagination"),
) -> Any:
    """
    List files from Google Drive.
    """
    logger.info(f"[GDRIVE] User {current_user.id} requesting files (folder: {folder_id or 'root'})")
    
    try:
        connection = await get_active_connection(session, current_user.id)
        logger.info(f"[GDRIVE] Connection found. Token expires: {connection.expires_at}")
    except HTTPException as e:
        logger.error(f"[GDRIVE] No active connection for user {current_user.id}: {e.detail}")
        raise

    try:
        result = await google_drive_service.list_files(
            access_token=connection.access_token,
            folder_id=folder_id,

            page_size=100, # Increased for better initial visibility
            page_token=page_token,
        )

        # Update last synced time
        connection.last_synced_at = datetime.now(timezone.utc)
        session.add(connection)
        session.commit()
        
        file_count = len(result.get('files', []))
        logger.info(f"[GDRIVE] Successfully listed {file_count} files for user {current_user.id}")

        # Use model_validate instead of **result for better performance and safety
        return GoogleDriveFilesList.model_validate(result).model_dump(by_alias=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GDRIVE] Failed to list files for user {current_user.id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Google Drive Error: {str(e)}"
        )




@router.post("/import")
async def import_file_from_google_drive(
    *,
    session: SessionDep,
    copilot_session: CopilotSessionDep,
    current_user: CurrentUser,
    import_request: ImportFileRequest,
) -> Any:
    """
    Import a file from Google Drive to copilot's knowledge base.

    Downloads the file from Google Drive and uploads it to the copilot's RAG system.
    """
    from app.copilot.models import Copilot

    logger.info(f"[GDRIVE] User {current_user.id} importing file {import_request.file_id} to copilot {import_request.copilot_id}")

    try:
        connection = await get_active_connection(session, current_user.id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GDRIVE] Failed to get connection: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

    # Verify copilot access
    copilot = copilot_session.get(Copilot, import_request.copilot_id)
    if not copilot:
        raise HTTPException(status_code=404, detail="Copilot not found")

    # Check if user has access to copilot (owner or workspace member)
    if copilot.created_by != current_user.id:
        if copilot.workspace_id is not None:
            raise HTTPException(status_code=403, detail="You don't have access to this copilot")

    try:
        # Download file from Google Drive
        logger.info(f"[GDRIVE] Downloading file {import_request.file_id}...")
        file_content, filename, mime_type = await google_drive_service.download_file(
            access_token=connection.access_token,
            file_id=import_request.file_id,
        )
        logger.info(f"[GDRIVE] Downloaded: {filename} ({mime_type}, {len(file_content)} bytes)")

        # Determine file type from MIME type
        mime_to_extension = {
            'application/pdf': 'pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
            'text/plain': 'txt',
            'text/markdown': 'md',
            'text/csv': 'csv',
        }

        file_type = mime_to_extension.get(mime_type)
        if not file_type:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {mime_type}"
            )

        # Create document record
        from app.copilot.models import CopilotDocument

        unique_filename = f"{uuid.uuid4()}.{file_type}"

        document = CopilotDocument(
            copilot_id=import_request.copilot_id,
            uploaded_by=current_user.id,
            filename=unique_filename,
            original_filename=filename,
            file_type=file_type,
            file_size=len(file_content),
            file_url="",  # Will be updated after R2 upload
            status="pending",
            title=filename,
            description=f"Imported from Google Drive",
        )
        copilot_session.add(document)
        copilot_session.commit()
        copilot_session.refresh(document)
        logger.info(f"[GDRIVE] Document record created: {document.id}")

        try:
            # Upload to R2 immediately
            from app.copilot.rag.storage import upload_to_r2
            
            file_url_r2 = await upload_to_r2(
                file_content=file_content,
                filename=unique_filename,
                content_type=f"application/{file_type}",
            )
            
            document.file_url = file_url_r2
            document.status = "processing"
            copilot_session.add(document)
            copilot_session.commit()
            
            # Dispatch task without content payload
            from app.copilot.tasks import process_document_task
            
            process_document_task.delay(
                document_id=str(document.id),
                file_content_base64=None, # Content already in R2
                file_type=file_type,
            )
            logger.info(f"[GDRIVE] Document {document.id} queued (content in R2)")
            
        except Exception as err:
            logger.error(f"[GDRIVE] Processing init failed: {str(err)}")
            document.status = "failed"
            document.error_message = f"Init failed: {str(err)}"
            copilot_session.add(document)
            copilot_session.commit()
            raise HTTPException(500, f"Processing initialization failed: {str(err)}")

        return {
            "message": "File imported successfully",
            "document_id": str(document.id),
            "filename": filename,
            "status": "processing"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GDRIVE] Import failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import file from Google Drive: {str(e)}"
        )

