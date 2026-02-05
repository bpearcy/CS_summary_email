"""
Outlook collector - fetches calendar events and emails via Microsoft Graph API.

Uses delegated permissions (refresh token) to access only the authenticated user's data.
"""

import os
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING
import requests

if TYPE_CHECKING:
    from ..auth import TokenManager


class OutlookCollector:
    """Collects calendar events and emails from Outlook via Microsoft Graph."""

    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, token_manager: "TokenManager"):
        """
        Initialize with a TokenManager for authentication.

        Args:
            token_manager: TokenManager instance for getting access tokens
        """
        self.token_manager = token_manager

    def _get_headers(self) -> dict:
        """Get headers for Graph API requests."""
        headers = self.token_manager.get_headers()
        headers["Prefer"] = 'outlook.timezone="Eastern Standard Time"'
        return headers

    def get_calendar_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Fetch calendar events for the specified date range.

        Args:
            start_date: Start of date range (default: 7 days ago)
            end_date: End of date range (default: now)

        Returns:
            List of calendar events with attendees
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        url = (
            f"{self.GRAPH_URL}/me/calendar/calendarView"
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
        folder: str = "inbox",
    ) -> list[dict]:
        """
        Fetch emails for the specified date range.

        Args:
            start_date: Start of date range (default: 7 days ago)
            end_date: End of date range (default: now)
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

        url = (
            f"{self.GRAPH_URL}/me/mailFolders/{folder}/messages"
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
    ) -> list[dict]:
        """Fetch sent emails for the specified date range."""
        return self.get_emails(
            start_date=start_date,
            end_date=end_date,
            folder="sentitems",
        )

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        save_to_sent: bool = True,
    ) -> bool:
        """
        Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML content of the email
            save_to_sent: Whether to save to sent items

        Returns:
            True if sent successfully
        """
        url = f"{self.GRAPH_URL}/me/sendMail"

        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_body,
                },
                "toRecipients": [
                    {"emailAddress": {"address": to}}
                ],
            },
            "saveToSentItems": save_to_sent,
        }

        response = requests.post(url, headers=self._get_headers(), json=email_data)

        if response.status_code == 202:
            return True
        else:
            print(f"Failed to send email: {response.status_code} - {response.text}")
            return False

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
