"""
Jira collector - fetches PRODOPS tickets via Jira API.

Configured for Street Diligence Jira instance.
Uses the POST /rest/api/3/search/jql endpoint for searching.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
import requests
from requests.auth import HTTPBasicAuth


# Default Jira URL for Street Diligence
DEFAULT_JIRA_URL = "https://streetdiligence.atlassian.net"

# Custom field for SD Client
CLIENT_FIELD = "customfield_11493"


class JiraCollector:
    """Collects PRODOPS tickets from Jira."""

    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.url = url or os.environ.get("JIRA_URL", DEFAULT_JIRA_URL)
        self.username = username or os.environ.get("JIRA_USERNAME")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN")
        self._auth = HTTPBasicAuth(self.username, self.api_token) if self.username and self.api_token else None

    def _search(self, jql: str, fields: list[str], max_results: int = 100) -> list[dict]:
        """
        Search for issues using the POST /rest/api/3/search/jql endpoint.

        This endpoint supports pagination via nextPageToken.
        """
        url = f"{self.url}/rest/api/3/search/jql"
        all_issues = []
        next_page_token = None

        while True:
            payload = {
                "jql": jql,
                "fields": fields,
                "maxResults": min(max_results - len(all_issues), 100),
            }
            if next_page_token:
                payload["nextPageToken"] = next_page_token

            response = requests.post(url, auth=self._auth, json=payload)

            if response.status_code != 200:
                print(f"    Jira search failed: {response.status_code} - {response.text[:200]}")
                break

            data = response.json()
            issues = data.get("issues", [])
            all_issues.extend(issues)

            # Check for more pages
            next_page_token = data.get("nextPageToken")
            if not next_page_token or len(all_issues) >= max_results:
                break

        return all_issues

    def get_client_tickets(
        self,
        client_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        statuses: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Fetch PRODOPS tickets for a specific client.

        Args:
            client_name: Client name (matches SD Client field)
            start_date: Start of date range (default: 7 days ago)
            end_date: End of date range (default: now)
            statuses: List of statuses to include (default: all open statuses)

        Returns:
            List of tickets
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        if statuses is None:
            statuses = ["Waiting for support", "Ticket Created", "Pending", "Escalated", "In Progress", "Resolved", "Canceled"]

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # Escape quotes in client name
        safe_client = client_name.replace('"', '\\"')

        # Build JQL - search for tickets updated in the date range for this client
        status_list = ", ".join([f'"{s}"' for s in statuses])
        jql = (
            f'project = PRODOPS AND issuetype = Support '
            f'AND "{CLIENT_FIELD}" ~ "{safe_client}" '
            f'AND updated >= "{start_str}" AND updated <= "{end_str}" '
            f'ORDER BY updated DESC'
        )

        issues = self._search(
            jql=jql,
            fields=["key", "summary", CLIENT_FIELD, "status", "created", "updated", "resolutiondate"],
            max_results=100,
        )

        return [
            {
                "key": issue["key"],
                "summary": issue["fields"].get("summary", ""),
                "client": issue["fields"].get(CLIENT_FIELD, ""),
                "status": issue["fields"].get("status", {}).get("name", ""),
                "created": issue["fields"].get("created", ""),
                "updated": issue["fields"].get("updated", ""),
                "resolved": issue["fields"].get("resolutiondate"),
            }
            for issue in issues
        ]

    def get_all_client_tickets(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, list[dict]]:
        """
        Fetch all PRODOPS tickets CREATED in the date range, grouped by client.

        Returns:
            Dict mapping client name to list of tickets
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # Get all PRODOPS Support tickets CREATED in the date range
        jql = (
            f'project = PRODOPS AND issuetype = Support '
            f'AND "{CLIENT_FIELD}" is not EMPTY '
            f'AND created >= "{start_str}" AND created <= "{end_str}" '
            f'ORDER BY created DESC'
        )

        print(f"    Jira JQL: {jql}")

        issues = self._search(
            jql=jql,
            fields=["key", "summary", CLIENT_FIELD, "status", "created", "updated", "resolutiondate"],
            max_results=500,
        )

        # Group by client
        by_client: dict[str, list[dict]] = {}
        for issue in issues:
            client = issue["fields"].get(CLIENT_FIELD, "Unknown")
            if client not in by_client:
                by_client[client] = []

            by_client[client].append({
                "key": issue["key"],
                "summary": issue["fields"].get("summary", ""),
                "status": issue["fields"].get("status", {}).get("name", ""),
                "created": issue["fields"].get("created", ""),
                "updated": issue["fields"].get("updated", ""),
                "resolved": issue["fields"].get("resolutiondate"),
            })

        return by_client

    def get_client_summary(
        self,
        client_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Get a summary of PRODOPS activity for a client.

        Args:
            client_name: Client name
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Summary dict with ticket counts and details
        """
        tickets = self.get_client_tickets(
            client_name=client_name,
            start_date=start_date,
            end_date=end_date,
        )

        # Count by status
        by_status: dict[str, int] = {}
        for ticket in tickets:
            status = ticket["status"]
            by_status[status] = by_status.get(status, 0) + 1

        # Count new vs resolved
        if start_date:
            new_tickets = [t for t in tickets if t["created"] >= str(start_date)]
        else:
            new_tickets = []
        resolved_tickets = [t for t in tickets if t["resolved"]]

        return {
            "client": client_name,
            "total_issues": len(tickets),
            "new_issues": len(new_tickets),
            "resolved_issues": len(resolved_tickets),
            "by_status": by_status,
            "by_type": {"Support": len(tickets)},
            "issues": tickets,
        }
