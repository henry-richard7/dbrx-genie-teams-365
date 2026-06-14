import os
import aiohttp
import urllib.parse
from datetime import datetime, timezone, timedelta
from config import DefaultConfig
import logging

logger = logging.getLogger(__name__)

CONFIG = DefaultConfig()

class OAuthHandler:
    """Handles OAuth 2.0 Authorization Code Flow for Azure Databricks via Entra ID."""
    
    def __init__(self):
        self.tenant_id = CONFIG.TENANT_ID or os.environ.get("TENANT_ID", "common")
        self.client_id = getattr(CONFIG, 'DATABRICKS_OAUTH_CLIENT_ID', None)
        self.client_secret = getattr(CONFIG, 'DATABRICKS_OAUTH_CLIENT_SECRET', None)
        self.redirect_uri = getattr(CONFIG, 'OAUTH_REDIRECT_URI', None)
        self.scope = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default offline_access openid profile"

    def is_configured(self) -> bool:
        """Returns True if the custom OAuth flow is configured with a redirect URI."""
        return bool(self.redirect_uri and self.client_id)

    def get_auth_url(self, state: str) -> str:
        """Generates the authorization URL for Azure AD to access Azure Databricks."""
        if not self.is_configured():
            raise ValueError("OAuth handler is not fully configured (missing redirect URI or client ID).")

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "response_mode": "query",
            "scope": self.scope,
            "state": state,
        }
        query_string = urllib.parse.urlencode(params)
        return f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/authorize?{query_string}"

    async def exchange_code(self, code: str) -> dict:
        """Exchanges the authorization code for access and refresh tokens.
        
        Returns:
            dict: The JSON response containing access_token, refresh_token, and expires_in.
        """
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "scope": self.scope,
            "code": code,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        
        if self.client_secret:
            data["client_secret"] = self.client_secret

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to exchange code: {error_text}")
                    raise Exception(f"Failed to exchange code: {response.status}")
                
                return await response.json()
                
    async def refresh_token(self, refresh_token_str: str) -> dict:
        """Refreshes the access token using the refresh token.
        
        Returns:
            dict: The JSON response containing access_token, refresh_token, and expires_in.
        """
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "scope": self.scope,
            "refresh_token": refresh_token_str,
            "grant_type": "refresh_token",
        }
        
        if self.client_secret:
            data["client_secret"] = self.client_secret

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to refresh token: {error_text}")
                    raise Exception(f"Failed to refresh token: {response.status}")
                
                return await response.json()
