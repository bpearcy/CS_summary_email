"""
Jira collector - fetches tickets and document submissions via Jira API.

Configured for Street Diligence Jira instance.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from jira import JIRA


# Default Jira URL for Street Diligence
DEFAULT_JIRA_URL = "https://streetdiligence.atlassian.net"


class JiraCollector:
    """Collects tickets and document submissions from Jira."""

    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.url = url or os.environ.get("JIRA_URL", DEFAULT_JIRA_URL)
        self.username = username or os.environ.get("JIRA_USERNAME")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN")
        self._jira: Optional[JIRA] = None

    def _connect(self) -> JIRA:
        """Connect to Jira."""
        if self._jira:
            return self._jira

        self._jira = JIRA(
            server=self.url,
            basic_auth=(self.username, self.api_token),
        )
        return self._jira

    def search_issues(
        self,
        jql: str,
        max_results: int = 100,
    ) -> list[dict]:
        """
        Search for issues using JQL.

        Args:
            jql: JQL query string
            max_results: Maximum results to return

        Returns:
            List of issues
        """
        jira = self._connect()
        issues = jira.search_issues(jql, maxResults=max_results)

        return [
            {
                "key": issue.key,
                "summary": issue.fields.summary,
                "status": issue.fields.status.name,
                "issue_type": issue.fields.issuetype.name,
                "priority": issue.fields.priority.name if issue.fields.priority else None,
                "assignee": issue.fields.assignee.displayName if issue.fields.assignee else None,
                "reporter": issue.fields.reporter.displayName if issue.fields.reporter else None,
                "created": str(issue.fields.created),
                "updated": str(issue.fields.updated),
                "resolved": str(issue.fields.resolutiondate) if issue.fields.resolutiondate else None,
                "labels": issue.fields.labels,
                "components": [c.name for c in issue.fields.components] if issue.fields.components else [],
            }
            for issue in issues
        ]

    def get_issues_by_label(
        self,
        label: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_resolved: bool = True,
    ) -> list[dict]:
        """
        Fetch issues by label within a date range.

        Args:
            label: Jira label to filter by
            start_date: Start of date range (default: 7 days ago)
            end_date: End of date range (default: now)
            include_resolved: Include resolved issues

        Returns:
            List of issues
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        jql = f'labels = "{label}" AND updated >= "{start_str}" AND updated <= "{end_str}"'

        if not include_resolved:
            jql += " AND resolution IS EMPTY"

        return self.search_issues(jql)

    def get_issues_by_project(
        self,
        project_key: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Fetch issues by project key within a date range.

        Args:
            project_key: Jira project key
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of issues
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        jql = f'project = "{project_key}" AND updated >= "{start_str}" AND updated <= "{end_str}"'

        return self.search_issues(jql)

    def get_document_submissions(
        self,
        client_identifier: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        issue_type: str = "Document Submission",
    ) -> list[dict]:
        """
        Fetch document submissions for a client.

        Args:
            client_identifier: Label or project key for the client
            start_date: Start of date range
            end_date: End of date range
            issue_type: Issue type for document submissions

        Returns:
            List of document submission issues
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # Try label first, fall back to text search
        jql = (
            f'(labels = "{client_identifier}" OR text ~ "{client_identifier}") '
            f'AND issuetype = "{issue_type}" '
            f'AND updated >= "{start_str}" AND updated <= "{end_str}"'
        )

        try:
            return self.search_issues(jql)
        except Exception:
            # Fall back to just label search if issue type doesn't exist
            jql = (
                f'labels = "{client_identifier}" '
                f'AND updated >= "{start_str}" AND updated <= "{end_str}"'
            )
            return self.search_issues(jql)

    def get_client_summary(
        self,
        client_label: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Get a summary of all Jira activity for a client.

        Args:
            client_label: Jira label for the client
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Summary dict with issues by status and type
        """
        issues = self.get_issues_by_label(
            label=client_label,
            start_date=start_date,
            end_date=end_date,
        )

        # Group by status
        by_status = {}
        for issue in issues:
            status = issue["status"]
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(issue)

        # Group by type
        by_type = {}
        for issue in issues:
            issue_type = issue["issue_type"]
            if issue_type not in by_type:
                by_type[issue_type] = []
            by_type[issue_type].append(issue)

        # Count new vs resolved
        new_issues = [i for i in issues if i["created"] >= str(start_date)]
        resolved_issues = [i for i in issues if i["resolved"]]

        return {
            "client": client_label,
            "total_issues": len(issues),
            "new_issues": len(new_issues),
            "resolved_issues": len(resolved_issues),
            "by_status": {k: len(v) for k, v in by_status.items()},
            "by_type": {k: len(v) for k, v in by_type.items()},
            "issues": issues,
        }
