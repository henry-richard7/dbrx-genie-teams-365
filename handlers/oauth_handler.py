"""
OAuth Authentication Handler Module.

This module provides the OAuthHandler class which is responsible for managing the
Custom OAuth (User-to-Machine) flow with Databricks.
"""
import os
import aiohttp
import urllib.parse
from datetime import datetime, timezone, timedelta
from config import DefaultConfig
import logging

logger = logging.getLogger(__name__)

CONFIG = DefaultConfig()


class OAuthHandler:
    """Handles OAuth 2.0 Authorization Code Flow for Databricks Native OAuth."""

    def __init__(self):
        """Initializes the OAuthHandler using values from the global config."""
        self.databricks_host = getattr(CONFIG, "DATABRICKS_HOST", None)
        self.client_id = getattr(CONFIG, "DATABRICKS_OAUTH_CLIENT_ID", None)
        self.client_secret = getattr(CONFIG, "DATABRICKS_OAUTH_CLIENT_SECRET", None)
        self.redirect_uri = getattr(CONFIG, "OAUTH_REDIRECT_URI", None)
        self.scope = "offline_access all-apis"

    def is_configured(self) -> bool:
        """Returns True if the custom OAuth flow is configured with a redirect URI."""
        return bool(self.redirect_uri and self.client_id and self.databricks_host)

    def get_auth_url(self, state: str) -> str:
        """Generates the authorization URL for Databricks."""
        if not self.is_configured():
            raise ValueError(
                "OAuth handler is not fully configured (missing redirect URI or client ID)."
            )

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
        }
        query_string = urllib.parse.urlencode(params)
        # Ensure host doesn't have a trailing slash
        host = self.databricks_host.rstrip("/")
        return f"{host}/oidc/v1/authorize?{query_string}"

    async def exchange_code(self, code: str) -> dict:
        """Exchanges the authorization code for access and refresh tokens.

        Returns:
            dict: The JSON response containing access_token, refresh_token, and expires_in.
        """
        host = self.databricks_host.rstrip("/")
        url = f"{host}/oidc/v1/token"

        data = {
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        auth = (
            aiohttp.BasicAuth(self.client_id, self.client_secret)
            if self.client_secret
            else None
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, auth=auth) as response:
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
        host = self.databricks_host.rstrip("/")
        url = f"{host}/oidc/v1/token"

        data = {
            "client_id": self.client_id,
            "refresh_token": refresh_token_str,
            "grant_type": "refresh_token",
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        auth = (
            aiohttp.BasicAuth(self.client_id, self.client_secret)
            if self.client_secret
            else None
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, auth=auth) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to refresh token: {error_text}")
                    raise Exception(f"Failed to refresh token: {response.status}")

                return await response.json()
