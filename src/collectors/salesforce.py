"""
Salesforce collector - fetches activities, opportunities, and tasks via Salesforce API.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from simple_salesforce import Salesforce


class SalesforceCollector:
    """Collects activities and opportunities from Salesforce."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_token: Optional[str] = None,
        domain: Optional[str] = None,
    ):
        self.username = username or os.environ.get("SF_USERNAME")
        self.password = password or os.environ.get("SF_PASSWORD")
        self.security_token = security_token or os.environ.get("SF_SECURITY_TOKEN")
        self.domain = domain or os.environ.get("SF_DOMAIN", "login")
        self._sf: Optional[Salesforce] = None

    def _connect(self) -> Salesforce:
        """Connect to Salesforce."""
        if self._sf:
            return self._sf

        self._sf = Salesforce(
            username=self.username,
            password=self.password,
            security_token=self.security_token,
            domain=self.domain,
        )
        return self._sf

    def get_accounts(self) -> list[dict]:
        """
        Fetch all active accounts.

        Returns:
            List of accounts with Id, Name, and other details
        """
        sf = self._connect()

        query = """
            SELECT Id, Name, Type, Industry, BillingCity, BillingState, OwnerId, Owner.Name
            FROM Account
            WHERE IsDeleted = false
            ORDER BY Name
        """

        result = sf.query_all(query)
        return result.get("records", [])

    def get_activities(
        self,
        account_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Fetch activities (tasks and events) for an account.

        Args:
            account_name: Filter by account name
            start_date: Start of date range (default: 7 days ago)
            end_date: End of date range (default: now)

        Returns:
            List of activities
        """
        sf = self._connect()

        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build account filter
        account_filter = ""
        if account_name:
            # Escape single quotes in account name
            safe_name = account_name.replace("'", "\\'")
            account_filter = f"AND Account.Name LIKE '%{safe_name}%'"

        # Query Tasks (completed activities)
        tasks_query = f"""
            SELECT Id, Subject, Description, Status, ActivityDate,
                   Account.Name, Owner.Name, WhoId, Who.Name, Type
            FROM Task
            WHERE CreatedDate >= {start_str}
              AND CreatedDate <= {end_str}
              {account_filter}
            ORDER BY ActivityDate DESC
        """

        # Query Events (meetings)
        events_query = f"""
            SELECT Id, Subject, Description, StartDateTime, EndDateTime,
                   Account.Name, Owner.Name, WhoId, Who.Name, Type
            FROM Event
            WHERE StartDateTime >= {start_str}
              AND StartDateTime <= {end_str}
              {account_filter}
            ORDER BY StartDateTime DESC
        """

        tasks_result = sf.query_all(tasks_query)
        events_result = sf.query_all(events_query)

        activities = []

        for task in tasks_result.get("records", []):
            activities.append({
                "type": "task",
                "subject": task.get("Subject", ""),
                "description": task.get("Description", ""),
                "status": task.get("Status", ""),
                "date": task.get("ActivityDate", ""),
                "account": task.get("Account", {}).get("Name", "") if task.get("Account") else "",
                "owner": task.get("Owner", {}).get("Name", "") if task.get("Owner") else "",
                "contact": task.get("Who", {}).get("Name", "") if task.get("Who") else "",
                "activity_type": task.get("Type", ""),
            })

        for event in events_result.get("records", []):
            activities.append({
                "type": "event",
                "subject": event.get("Subject", ""),
                "description": event.get("Description", ""),
                "start": event.get("StartDateTime", ""),
                "end": event.get("EndDateTime", ""),
                "account": event.get("Account", {}).get("Name", "") if event.get("Account") else "",
                "owner": event.get("Owner", {}).get("Name", "") if event.get("Owner") else "",
                "contact": event.get("Who", {}).get("Name", "") if event.get("Who") else "",
                "activity_type": event.get("Type", ""),
            })

        return activities

    def get_opportunities(
        self,
        account_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Fetch opportunities updated in the date range.

        Args:
            account_name: Filter by account name
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of opportunities
        """
        sf = self._connect()

        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        account_filter = ""
        if account_name:
            safe_name = account_name.replace("'", "\\'")
            account_filter = f"AND Account.Name LIKE '%{safe_name}%'"

        query = f"""
            SELECT Id, Name, StageName, Amount, CloseDate, Probability,
                   Account.Name, Owner.Name, LastModifiedDate
            FROM Opportunity
            WHERE LastModifiedDate >= {start_str}
              AND LastModifiedDate <= {end_str}
              {account_filter}
            ORDER BY LastModifiedDate DESC
        """

        result = sf.query_all(query)

        return [
            {
                "name": opp.get("Name", ""),
                "stage": opp.get("StageName", ""),
                "amount": opp.get("Amount"),
                "close_date": opp.get("CloseDate", ""),
                "probability": opp.get("Probability"),
                "account": opp.get("Account", {}).get("Name", "") if opp.get("Account") else "",
                "owner": opp.get("Owner", {}).get("Name", "") if opp.get("Owner") else "",
                "last_modified": opp.get("LastModifiedDate", ""),
            }
            for opp in result.get("records", [])
        ]

    def get_client_summary(
        self,
        client_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Get a summary of all Salesforce activity for a client.

        Args:
            client_name: Client/Account name
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Summary dict with activities, opportunities, etc.
        """
        activities = self.get_activities(
            account_name=client_name,
            start_date=start_date,
            end_date=end_date,
        )

        opportunities = self.get_opportunities(
            account_name=client_name,
            start_date=start_date,
            end_date=end_date,
        )

        tasks = [a for a in activities if a["type"] == "task"]
        events = [a for a in activities if a["type"] == "event"]

        return {
            "client": client_name,
            "tasks": tasks,
            "events": events,
            "opportunities": opportunities,
            "task_count": len(tasks),
            "event_count": len(events),
            "opportunity_count": len(opportunities),
        }
