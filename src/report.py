"""
Report generator - aggregates data from all collectors and formats the email.
"""

from datetime import datetime, timedelta
from typing import Optional
from jinja2 import Environment, FileSystemLoader
import os


class ReportGenerator:
    """Generates weekly client summary report."""

    def __init__(
        self,
        template_dir: Optional[str] = None,
    ):
        if template_dir is None:
            template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")

        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )

    def aggregate_client_data(
        self,
        client_name: str,
        outlook_data: dict,
        salesforce_data: dict,
        datadog_data: dict,
        jira_data: dict,
    ) -> dict:
        """
        Aggregate data from all sources for a single client.

        Returns:
            Combined client summary
        """
        return {
            "name": client_name,
            "calendar": {
                "meetings": outlook_data.get("events", []),
                "meeting_count": len(outlook_data.get("events", [])),
            },
            "email": {
                "received": outlook_data.get("emails_received", []),
                "sent": outlook_data.get("emails_sent", []),
                "received_count": len(outlook_data.get("emails_received", [])),
                "sent_count": len(outlook_data.get("emails_sent", [])),
            },
            "salesforce": {
                "tasks": salesforce_data.get("tasks", []),
                "events": salesforce_data.get("events", []),
                "opportunities": salesforce_data.get("opportunities", []),
                "task_count": salesforce_data.get("task_count", 0),
                "event_count": salesforce_data.get("event_count", 0),
                "opportunity_count": salesforce_data.get("opportunity_count", 0),
            },
            "usage": {
                "metrics": datadog_data.get("metrics", {}),
                "monitors": datadog_data.get("monitors", []),
                "monitor_summary": datadog_data.get("monitor_summary", {}),
                "time_on_platform": datadog_data.get("time_on_platform", 0),
            },
            "jira": {
                "issues": jira_data.get("issues", []),
                "total_issues": jira_data.get("total_issues", 0),
                "new_issues": jira_data.get("new_issues", 0),
                "resolved_issues": jira_data.get("resolved_issues", 0),
                "by_status": jira_data.get("by_status", {}),
                "by_type": jira_data.get("by_type", {}),
            },
            "has_activity": self._has_activity(
                outlook_data, salesforce_data, datadog_data, jira_data
            ),
        }

    def _has_activity(
        self,
        outlook_data: dict,
        salesforce_data: dict,
        datadog_data: dict,
        jira_data: dict,
    ) -> bool:
        """Check if client has any activity this period."""
        return any([
            outlook_data.get("events"),
            outlook_data.get("emails_received"),
            outlook_data.get("emails_sent"),
            salesforce_data.get("tasks"),
            salesforce_data.get("events"),
            salesforce_data.get("opportunities"),
            jira_data.get("issues"),
        ])

    def generate_report(
        self,
        clients_data: list[dict],
        start_date: datetime,
        end_date: datetime,
        include_inactive: bool = False,
    ) -> str:
        """
        Generate HTML report from aggregated client data.

        Args:
            clients_data: List of aggregated client data dicts
            start_date: Report period start
            end_date: Report period end
            include_inactive: Include clients with no activity

        Returns:
            HTML report string
        """
        # Filter inactive clients if requested
        if not include_inactive:
            clients_data = [c for c in clients_data if c.get("has_activity", True)]

        # Sort alphabetically
        clients_data.sort(key=lambda c: c["name"].lower())

        # Calculate summary stats
        summary = {
            "total_clients": len(clients_data),
            "total_meetings": sum(c["calendar"]["meeting_count"] for c in clients_data),
            "total_emails_received": sum(c["email"]["received_count"] for c in clients_data),
            "total_emails_sent": sum(c["email"]["sent_count"] for c in clients_data),
            "total_jira_issues": sum(c["jira"]["total_issues"] for c in clients_data),
            "total_new_issues": sum(c["jira"]["new_issues"] for c in clients_data),
            "total_resolved_issues": sum(c["jira"]["resolved_issues"] for c in clients_data),
        }

        template = self.env.get_template("email_template.html")

        return template.render(
            clients=clients_data,
            summary=summary,
            start_date=start_date.strftime("%B %d, %Y"),
            end_date=end_date.strftime("%B %d, %Y"),
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        )

    def generate_plain_text(
        self,
        clients_data: list[dict],
        start_date: datetime,
        end_date: datetime,
    ) -> str:
        """
        Generate plain text report (fallback for email clients that don't support HTML).
        """
        lines = [
            f"Weekly Client Summary",
            f"Period: {start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}",
            "=" * 60,
            "",
        ]

        for client in sorted(clients_data, key=lambda c: c["name"].lower()):
            if not client.get("has_activity"):
                continue

            lines.append(f"\n{client['name']}")
            lines.append("-" * len(client['name']))

            # Calendar
            meeting_count = client["calendar"]["meeting_count"]
            if meeting_count:
                lines.append(f"  Meetings: {meeting_count}")
                for meeting in client["calendar"]["meetings"][:3]:
                    lines.append(f"    - {meeting.get('subject', 'No subject')}")

            # Email
            email_in = client["email"]["received_count"]
            email_out = client["email"]["sent_count"]
            if email_in or email_out:
                lines.append(f"  Emails: {email_in} received, {email_out} sent")

            # Salesforce
            sf = client["salesforce"]
            if sf["task_count"] or sf["event_count"] or sf["opportunity_count"]:
                lines.append(f"  Salesforce: {sf['task_count']} tasks, {sf['event_count']} events, {sf['opportunity_count']} opportunities")

            # Jira
            jira = client["jira"]
            if jira["total_issues"]:
                lines.append(f"  Jira: {jira['new_issues']} new, {jira['resolved_issues']} resolved")

            lines.append("")

        return "\n".join(lines)
