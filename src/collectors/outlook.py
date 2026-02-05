"""
Outlook collector - fetches calendar events and emails via Microsoft Graph API.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
import msal
import requests


class OutlookCollector:
    """Collects calendar events and emails from Outlook via Microsoft Graph."""

    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        self.client_id = client_id or os.environ.get("MS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("MS_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.environ.get("MS_TENANT_ID")
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
            "Prefer": 'outlook.timezone="Eastern Standard Time"',
        }

    def get_calendar_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_email: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch calendar events for the specified date range.

        Args:
            start_date: Start of date range (default: 7 days ago)
            end_date: End of date range (default: now)
            user_email: User's email for delegated access

        Returns:
            List of calendar events with attendees
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Use /me for the authenticated user or /users/{email} for specific user
        base = f"{self.GRAPH_URL}/me" if not user_email else f"{self.GRAPH_URL}/users/{user_email}"

        url = (
            f"{base}/calendar/calendarView"
            f"?startDateTime={start_str}"
            f"&endDateTime={end_str}"
            f"&$select=subject,start,end,attendees,organizer,location,isOnlineMeeting"
            f"&$orderby=start/dateTime"
            f"&$top=100"
        )

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()

        events = response.json().get("value", [])

        return [
            {
                "subject": event.get("subject", ""),
                "start": event.get("start", {}).get("dateTime", ""),
                "end": event.get("end", {}).get("dateTime", ""),
                "attendees": [
                    {
                        "email": att.get("emailAddress", {}).get("address", ""),
                        "name": att.get("emailAddress", {}).get("name", ""),
                        "response": att.get("status", {}).get("response", ""),
                    }
                    for att in event.get("attendees", [])
                ],
                "organizer": event.get("organizer", {}).get("emailAddress", {}).get("address", ""),
                "location": event.get("location", {}).get("displayName", ""),
                "is_online": event.get("isOnlineMeeting", False),
            }
            for event in events
        ]

    def get_emails(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_email: Optional[str] = None,
        folder: str = "inbox",
    ) -> list[dict]:
        """
        Fetch emails for the specified date range.

        Args:
            start_date: Start of date range (default: 7 days ago)
            end_date: End of date range (default: now)
            user_email: User's email for delegated access
            folder: Mail folder to search

        Returns:
            List of emails with sender/recipient info
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        base = f"{self.GRAPH_URL}/me" if not user_email else f"{self.GRAPH_URL}/users/{user_email}"

        url = (
            f"{base}/mailFolders/{folder}/messages"
            f"?$filter=receivedDateTime ge {start_str} and receivedDateTime le {end_str}"
            f"&$select=subject,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments"
            f"&$orderby=receivedDateTime desc"
            f"&$top=500"
        )

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()

        emails = response.json().get("value", [])

        return [
            {
                "subject": email.get("subject", ""),
                "from": email.get("from", {}).get("emailAddress", {}).get("address", ""),
                "from_name": email.get("from", {}).get("emailAddress", {}).get("name", ""),
                "to": [
                    r.get("emailAddress", {}).get("address", "")
                    for r in email.get("toRecipients", [])
                ],
                "cc": [
                    r.get("emailAddress", {}).get("address", "")
                    for r in email.get("ccRecipients", [])
                ],
                "received": email.get("receivedDateTime", ""),
                "has_attachments": email.get("hasAttachments", False),
            }
            for email in emails
        ]

    def get_sent_emails(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_email: Optional[str] = None,
    ) -> list[dict]:
        """Fetch sent emails for the specified date range."""
        return self.get_emails(
            start_date=start_date,
            end_date=end_date,
            user_email=user_email,
            folder="sentitems",
        )

    def filter_by_client(
        self,
        events_or_emails: list[dict],
        client_name: str,
        client_domains: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Filter events or emails to those involving a specific client.

        Args:
            events_or_emails: List of events or emails
            client_name: Client name to search for
            client_domains: Email domains associated with client

        Returns:
            Filtered list matching the client
        """
        results = []
        client_lower = client_name.lower()
        domains = [d.lower() for d in (client_domains or [])]

        for item in events_or_emails:
            matched = False

            # Check subject for client name
            subject = item.get("subject", "").lower()
            if client_lower in subject:
                matched = True

            # Check attendees (for events)
            if "attendees" in item and not matched:
                for att in item["attendees"]:
                    email = att.get("email", "").lower()
                    name = att.get("name", "").lower()
                    if client_lower in name or any(d in email for d in domains):
                        matched = True
                        break

            # Check from/to (for emails)
            if "from" in item and not matched:
                from_email = item.get("from", "").lower()
                if any(d in from_email for d in domains):
                    matched = True

            if "to" in item and not matched:
                for to_email in item.get("to", []):
                    if any(d in to_email.lower() for d in domains):
                        matched = True
                        break

            if matched:
                results.append(item)

        return results
