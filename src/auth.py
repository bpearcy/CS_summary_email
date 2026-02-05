"""
Microsoft Graph authentication using refresh tokens (delegated permissions).

This module handles token refresh for the GitHub Action, using a refresh token
that was obtained through interactive login.
"""

import os
from typing import Optional
import requests

# Azure AD App Configuration
CLIENT_ID = os.environ.get("MS_CLIENT_ID", "d679d9d3-5dd1-454f-b3dd-53f3a9b909c3")
TENANT_ID = os.environ.get("MS_TENANT_ID", "1cdfbb46-a98c-40e1-9173-60fda279a56c")

SCOPES = [
    "offline_access",
    "Calendars.Read",
    "Mail.Read",
    "Mail.Send",
    "Files.Read",
    "User.Read",
]


class TokenManager:
    """Manages Microsoft Graph access tokens using refresh tokens."""

    def __init__(
        self,
        refresh_token: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        self.refresh_token = refresh_token or os.environ.get("MS_REFRESH_TOKEN")
        self.client_id = client_id or CLIENT_ID
        self.tenant_id = tenant_id or TENANT_ID
        self._access_token: Optional[str] = None
        self._user_email: Optional[str] = None

        if not self.refresh_token:
            raise ValueError(
                "No refresh token provided. Set MS_REFRESH_TOKEN environment variable "
                "or run scripts/get_refresh_token.py to obtain one."
            )

    def _refresh_access_token(self) -> dict:
        """Use refresh token to get a new access token."""
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

        data = {
            "client_id": self.client_id,
            "scope": " ".join(SCOPES),
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        response = requests.post(token_url, data=data)
        result = response.json()

        if "error" in result:
            raise Exception(
                f"Token refresh failed: {result.get('error')} - {result.get('error_description')}"
            )

        return result

    def get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        if self._access_token:
            return self._access_token

        tokens = self._refresh_access_token()
        self._access_token = tokens["access_token"]

        # Update refresh token if a new one was issued
        if "refresh_token" in tokens:
            self.refresh_token = tokens["refresh_token"]

        return self._access_token

    def get_headers(self) -> dict:
        """Get headers for Microsoft Graph API requests."""
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
        }

    def get_user_email(self) -> str:
        """Get the email address of the authenticated user."""
        if self._user_email:
            return self._user_email

        response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers=self.get_headers(),
        )
        response.raise_for_status()

        user = response.json()
        self._user_email = user.get("mail") or user.get("userPrincipalName")

        return self._user_email

    def verify_connection(self) -> dict:
        """Verify the connection and return user info."""
        response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers=self.get_headers(),
        )
        response.raise_for_status()

        user = response.json()
        return {
            "display_name": user.get("displayName"),
            "email": user.get("mail") or user.get("userPrincipalName"),
            "id": user.get("id"),
        }
