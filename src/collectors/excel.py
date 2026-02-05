"""
Excel Online collector - reads client list from Excel spreadsheet via Microsoft Graph API.

Uses delegated permissions (refresh token) to access the authenticated user's OneDrive.
"""

import os
from typing import Optional, TYPE_CHECKING
import requests

if TYPE_CHECKING:
    from ..auth import TokenManager


class ExcelCollector:
    """Reads client list from Excel Online spreadsheet."""

    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        token_manager: "TokenManager",
        file_id: Optional[str] = None,
        file_path: Optional[str] = None,
    ):
        """
        Initialize with a TokenManager for authentication.

        Args:
            token_manager: TokenManager instance for getting access tokens
            file_id: OneDrive file ID (preferred)
            file_path: Path to file in OneDrive (e.g., "/Documents/Clients.xlsx")
        """
        self.token_manager = token_manager
        self.file_id = file_id or os.environ.get("EXCEL_FILE_ID")
        self.file_path = file_path or os.environ.get("EXCEL_FILE_PATH")

    def _get_headers(self) -> dict:
        """Get headers for Graph API requests."""
        return self.token_manager.get_headers()

    def _get_file_url(self) -> str:
        """Get the Graph API URL for the Excel file."""
        if self.file_id:
            return f"{self.GRAPH_URL}/me/drive/items/{self.file_id}"
        elif self.file_path:
            # URL-encode the path
            encoded_path = self.file_path.replace("/", ":/").rstrip(":")
            return f"{self.GRAPH_URL}/me/drive/root:{encoded_path}:"
        else:
            raise ValueError("Either file_id or file_path must be provided")

    def find_file(self, filename: str) -> Optional[dict]:
        """
        Search for a file by name in the user's OneDrive.

        Args:
            filename: Name of the file to search for

        Returns:
            File info dict with id, name, webUrl, or None if not found
        """
        url = f"{self.GRAPH_URL}/me/drive/root/search(q='{filename}')"

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()

        files = response.json().get("value", [])

        for f in files:
            if f.get("name", "").lower() == filename.lower():
                return {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "web_url": f.get("webUrl"),
                }

        # Return first match if exact match not found
        if files:
            f = files[0]
            return {
                "id": f.get("id"),
                "name": f.get("name"),
                "web_url": f.get("webUrl"),
            }

        return None

    def get_clients(self, worksheet: str = "Security Requirements") -> list[dict]:
        """
        Fetch client list from Excel Online.

        Args:
            worksheet: Name of the worksheet to read

        Returns:
            List of dicts with client info
        """
        file_url = self._get_file_url()
        url = f"{file_url}/workbook/worksheets/{worksheet}/usedRange"

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()

        data = response.json()
        values = data.get("values", [])

        if not values:
            return []

        # First row is headers
        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(values[0])]
        clients = []

        for row in values[1:]:
            if not row or not row[0]:  # Skip empty rows
                continue

            client = {
                "name": str(row[0]).strip() if len(row) > 0 and row[0] else "",
                "data_location_requirements": str(row[1]).strip() if len(row) > 1 and row[1] else "",
                "subcontractor_requirements": str(row[2]).strip() if len(row) > 2 and row[2] else "",
            }

            # Only add if there's a client name
            if client["name"]:
                clients.append(client)

        # Sort alphabetically by name
        clients.sort(key=lambda c: c["name"].lower())

        return clients

    def get_client_names(self) -> list[str]:
        """Get just the list of client names, sorted alphabetically."""
        clients = self.get_clients()
        return [c["name"] for c in clients]
