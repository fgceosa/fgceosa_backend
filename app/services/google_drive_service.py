"""
Google Drive Service
Handles OAuth authentication and file operations with Google Drive
"""
import io
import logging
from datetime import datetime, timezone
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
import httpx


from app.core.config import settings

logger = logging.getLogger(__name__)


class GoogleDriveService:
    """Service for interacting with Google Drive API"""

    # OAuth 2.0 scopes
    # Note: openid is automatically included by Google
    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'openid',  # Explicitly include openid to match Google's response
    ]

    # Supported file types for import
    SUPPORTED_MIME_TYPES = {
        # Google Workspace formats
        'application/vnd.google-apps.document': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.google-apps.spreadsheet': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.google-apps.presentation': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',

        # Direct downloads
        'application/pdf': None,
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': None,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': None,
        'text/plain': None,
        'text/markdown': None,
        'text/csv': None,
    }

    def __init__(self):
        """Initialize Google Drive service"""
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI

        # Validate credentials
        if not self.client_id or not self.client_secret:
            logger.warning("Google Drive credentials not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")

        # Check if credentials look valid (Google Client IDs end with .apps.googleusercontent.com)
        if self.client_id and not self.client_id.endswith('.apps.googleusercontent.com'):
            logger.warning(f"GOOGLE_CLIENT_ID appears invalid. Expected format: xxx.apps.googleusercontent.com, got: {self.client_id}")

    def create_oauth_flow(self, state: str | None = None) -> Flow:
        """
        Create OAuth2 flow for Google Drive authentication.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Configured Flow object
        """
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=self.SCOPES,
            state=state,
        )
        flow.redirect_uri = self.redirect_uri
        return flow

    def get_authorization_url(self, state: str) -> str:
        """
        Generate OAuth2 authorization URL.

        Args:
            state: State parameter for CSRF protection

        Returns:
            Authorization URL
        """
        flow = self.create_oauth_flow(state)
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent to get refresh token
        )
        logger.info(f"Generated Google OAuth URL: {authorization_url[:100]}...")
        return authorization_url

    async def exchange_code_for_tokens(self, code: str, state: str) -> dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.
        """
        try:
            flow = self.create_oauth_flow(state)
            flow.fetch_token(code=code)
            credentials = flow.credentials

            # Check if we got the Drive scope
            granted_scopes = getattr(credentials, 'scopes', [])
            if not isinstance(granted_scopes, list):
                granted_scopes = []
                
            requested_scopes = set(self.SCOPES)
            granted_scopes_set = set(granted_scopes)
            missing_scopes = requested_scopes - granted_scopes_set

            if 'https://www.googleapis.com/auth/drive.readonly' in missing_scopes:
                logger.error(f"Drive scope missing. Granted: {granted_scopes}")
                raise ValueError("Permission Denied: Please check 'See your Google Drive files' during sign-in.")

            logger.info(f"Successfully exchanged tokens. Granted: {granted_scopes}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to exchange code for tokens: {error_msg}")
            
            if "Scope has changed" in error_msg:
                # User likely unchecked the Drive permission box
                raise ValueError("Connection Failed: You did not grant permission to access Google Drive files. Please try again and ensure you check the box to 'See your Google Drive files'.")
            
            raise ValueError(error_msg)

        # Get user info via direct HTTP to avoid discovery hangs
        url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {credentials.token}"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url, headers=headers)
                user_info = resp.json() if resp.status_code == 200 else {}
            except Exception as e:
                logger.error(f"User info fetch failed: {str(e)}")
                user_info = {}

        return {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_type': 'Bearer',
            'expires_at': credentials.expiry,
            'scopes': credentials.scopes,
            'user_email': user_info.get('email'),
            'user_id': user_info.get('id'),
            'user_name': user_info.get('name'),
        }





    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """
        Refresh access token using httpx (Async).
        """
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        
        logger.info(f"Refreshing Google access token for client {self.client_id[:10]}...")
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, data=data)
                if resp.status_code != 200:
                    error_detail = resp.text
                    logger.error(f"OAuth Refresh Failed (Status {resp.status_code}): {error_detail}")
                    if "invalid_grant" in error_detail:
                        raise ValueError("Google session expired or revoked. Please reconnect.")
                    raise Exception(f"OAuth Refresh Failed ({resp.status_code})")
                    
                token_data = resp.json()
                
                # Calculate expiry
                from datetime import timedelta
                expires_in = token_data.get('expires_in', 3600)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                
                logger.info("Successfully refreshed Google access token.")
                return {
                    'access_token': token_data['access_token'],
                    'expires_at': expires_at,
                }
            except httpx.NetworkError as ne:
                logger.error(f"Network error during token refresh: {str(ne)}")
                raise Exception("Network Error: Could not reach Google auth servers.")
            except Exception as e:
                logger.error(f"Unexpected error during token refresh: {str(e)}")
                raise e



    async def list_files(
        self,
        access_token: str,
        folder_id: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        List files in Google Drive using direct HTTP (Async).
        """
        logger.info(f"Listing Google Drive files via direct HTTP (Async). Folder ID: {folder_id or 'root'}")
        
        try:
            url = "https://www.googleapis.com/drive/v3/files"
            
            query_parts = ["trashed = false"]
            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")
            else:
                query_parts.append("'root' in parents")

            params = {
                "q": " and ".join(query_parts),
                "pageSize": page_size,
                "fields": "nextPageToken, files(id, name, mimeType, size, modifiedTime, iconLink, webViewLink, parents)",
                "orderBy": "folder,name",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            
            if page_token:
                params["pageToken"] = page_token

                
            headers = {"Authorization": f"Bearer {access_token}"}
            
            # Set generous timeouts for Google Drive browsing
            timeout = httpx.Timeout(30.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                try:
                    response = await client.get(url, params=params, headers=headers)

                except httpx.NetworkError as ne:
                    logger.error(f"Network error listing Google Drive files: {str(ne)}")
                    raise Exception("Network Error: Could not reach Google Drive APIs. Check internet.")
                except httpx.TimeoutException:
                    logger.error("Timeout listing Google Drive files.")
                    raise Exception("Request Timeout: Google Drive is taking too long to respond.")
                
                if response.status_code != 200:
                    error_msg = response.text
                    logger.error(f"Google Drive API error: {error_msg}")
                    
                    if "insufficientPermissions" in error_msg:
                        raise ValueError("Permission Denied: Please reconnect and grant 'View files' permission.")
                    
                    if response.status_code == 401:
                        raise ValueError("Unauthorized: Your Google session expired. Please reconnect.")
                        
                    raise Exception(f"Google Drive Error ({response.status_code})")
                
                results = response.json()
            
            files = results.get('files', [])
            
            # Fallback: If empty and at root, try to find ANY supported files (Shared with me, etc.)
            if not files and not folder_id:
                try:
                    logger.warning(f"Root folder returned 0 files. Attempting broader fallback search...")
                    fallback_params = params.copy()
                    # Broad search for supported types that aren't trashed
                    fallback_params["q"] = "trashed = false" 
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        fallback_resp = await client.get(url, params=fallback_params, headers=headers)
                        if fallback_resp.status_code == 200:
                            fallback_results = fallback_resp.json()
                            files = fallback_results.get('files', [])
                            if files:
                                logger.info(f"Fallback search found {len(files)} files.")
                except Exception as fe:
                    logger.error(f"Fallback search failed: {str(fe)}")

            
            next_page_token = results.get('nextPageToken')
            logger.info(f"Successfully retrieved {len(files)} items from Google Drive.")




            # Format files for frontend
            formatted_files = []
            for file in files:
                try:
                    f_id = file.get('id')
                    f_name = file.get('name', 'Untitled')
                    f_mime = file.get('mimeType', 'application/octet-stream')
                    
                    is_folder = f_mime == 'application/vnd.google-apps.folder'
                    is_supported = is_folder or (f_mime in self.SUPPORTED_MIME_TYPES)

                    # Handle missing size or string size
                    raw_size = file.get('size', 0)
                    try:
                        f_size = int(raw_size)
                    except (ValueError, TypeError):
                        f_size = 0

                    formatted_files.append({
                        'id': f_id,
                        'name': f_name,
                        'mime_type': f_mime,
                        'size': f_size if not is_folder else 0,
                        'modified_time': file.get('modified_time') or file.get('modifiedTime'),
                        'icon_url': file.get('iconLink'),
                        'web_view_link': file.get('webViewLink'),
                        'is_folder': is_folder,
                        'is_supported': is_supported,
                        'can_import': is_supported and not is_folder,
                    })

                except Exception as fe:
                    logger.error(f"Error formatting file {file.get('id')}: {str(fe)}")
                    continue

            return {
                'files': formatted_files,
                'next_page_token': next_page_token,
            }
        except Exception as e:
            logger.error(f"Google Drive API error in list_files: {str(e)}")
            raise e



    async def download_file(self, access_token: str, file_id: str) -> tuple[bytes, str, str]:
        """
        Download file from Google Drive using direct HTTP (Async).
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Get metadata
            meta_url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
            resp = await client.get(meta_url, params={"fields": "name,mimeType,size", "supportsAllDrives": "true"}, headers=headers)
            if resp.status_code != 200:
                raise Exception(f"Failed to get file metadata: {resp.text}")
            meta = resp.json()

            
            filename = meta['name']
            mime_type = meta['mimeType']
            
            # 2. Download content
            export_mime_type = self.SUPPORTED_MIME_TYPES.get(mime_type)
            
            if export_mime_type:
                # Export Google native files (Docs, Sheets, Slides)
                download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
                params = {"mimeType": export_mime_type}
                mime_type = export_mime_type
            else:
                # Download binary/regular files
                download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
                params = {"alt": "media", "supportsAllDrives": "true"}
                
            resp = await client.get(download_url, params=params, headers=headers)

            if resp.status_code != 200:
                raise Exception(f"Failed to download file {file_id}: {resp.text}")
            content = resp.content
            
        return content, filename, mime_type



    async def get_file_metadata(self, access_token: str, file_id: str) -> dict[str, Any]:
        """
        Get file metadata from Google Drive using direct HTTP (Async).
        """
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        params = {
            "fields": "id,name,mimeType,size,modifiedTime,createdTime,owners,webViewLink",
            "supportsAllDrives": "true"
        }
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                raise Exception(f"Failed to get file metadata: {resp.text}")
            return resp.json()





# Global service instance
google_drive_service = GoogleDriveService()
