"""
Excel Online collector - reads client list from Excel spreadsheet via Microsoft Graph API.
"""

import os
from typing import Optional
import msal
import requests


class ExcelCollector:
    """Reads client list from Excel Online spreadsheet."""

    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        file_id: Optional[str] = None,
    ):
        self.client_id = client_id or os.environ.get("MS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("MS_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.environ.get("MS_TENANT_ID")
        self.file_id = file_id or os.environ.get("EXCEL_FILE_ID")
        self._access_token: Optional[str] = None

    def _get_access_token(self) -> str:
        """Get Microsoft Graph access token using client credentials flow."""
        if self._access_token:
            return self._access_token

        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=authority,
            client_credential=self.client_secret,
        )

        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" not in result:
            raise Exception(f"Failed to get access token: {result.get('error_description')}")

        self._access_token = result["access_token"]
        return self._access_token

    def _get_headers(self) -> dict:
        """Get headers for Graph API requests."""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def get_clients(self) -> list[dict]:
        """
        Fetch client list from Excel Online.

        Returns list of dicts with client info:
        [
            {
                "name": "Client Name",
                "data_location_requirements": "...",
                "subcontractor_requirements": "...",
            },
            ...
        ]
        """
        # Read the used range from the first worksheet
        url = f"{self.GRAPH_URL}/me/drive/items/{self.file_id}/workbook/worksheets/Sheet1/usedRange"

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()

        data = response.json()
        values = data.get("values", [])

        if not values:
            return []

        # First row is headers
        headers = values[0]
        clients = []

        for row in values[1:]:
            if not row or not row[0]:  # Skip empty rows
                continue

            client = {
                "name": row[0] if len(row) > 0 else "",
                "data_location_requirements": row[1] if len(row) > 1 else "",
                "subcontractor_requirements": row[2] if len(row) > 2 else "",
            }

            # Only add if there's a client name
            if client["name"] and str(client["name"]).strip():
                clients.append(client)

        # Sort alphabetically by name
        clients.sort(key=lambda c: c["name"].lower())

        return clients

    def get_client_names(self) -> list[str]:
        """Get just the list of client names, sorted alphabetically."""
        clients = self.get_clients()
        return [c["name"] for c in clients]
