"""
Main orchestrator - coordinates data collection and report generation.

Uses delegated permissions (refresh token) to access only the authenticated user's data.
"""

import os
import sys
from datetime import datetime, timedelta

from auth import TokenManager
from collectors import (
    ExcelCollector,
    OutlookCollector,
    SalesforceCollector,
    DatadogCollector,
    JiraCollector,
)
from report import ReportGenerator


def get_date_range(lookback_days: int = 7) -> tuple[datetime, datetime]:
    """Get the date range for the report."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=lookback_days)
    return start_date, end_date


def main():
    """Main entry point."""
    print("Starting Weekly Client Summary Report Generation...")
    print("=" * 60)

    # Initialize Microsoft Graph authentication
    print("\nAuthenticating with Microsoft Graph...")
    try:
        token_manager = TokenManager()
        user_info = token_manager.verify_connection()
        print(f"  Authenticated as: {user_info['display_name']} ({user_info['email']})")
    except Exception as e:
        print(f"ERROR: Microsoft authentication failed: {e}")
        sys.exit(1)

    recipient_email = user_info["email"]

    # Initialize collectors
    print("\nInitializing collectors...")

    excel_collector = ExcelCollector(token_manager=token_manager)
    print("  - Excel collector initialized")

    outlook_collector = OutlookCollector(token_manager=token_manager)
    print("  - Outlook collector initialized")

    # Optional collectors - initialize if credentials provided
    salesforce_collector = None
    if os.environ.get("SF_USERNAME"):
        salesforce_collector = SalesforceCollector()
        print("  - Salesforce collector initialized")

    datadog_collector = None
    if os.environ.get("DD_API_KEY"):
        datadog_collector = DatadogCollector()
        print("  - Datadog collector initialized")

    jira_collector = None
    if os.environ.get("JIRA_API_TOKEN"):
        jira_collector = JiraCollector()
        print("  - Jira collector initialized")

    # Get date range
    start_date, end_date = get_date_range(7)
    print(f"\nReport period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # Get client list
    print("\nFetching client list from Excel...")
    try:
        clients = excel_collector.get_clients()
        print(f"  Found {len(clients)} clients")
    except Exception as e:
        print(f"  ERROR: Failed to fetch client list: {e}")
        print("  Continuing with empty client list...")
        clients = []

    # Fetch Outlook data (calendar events and emails)
    print("\nFetching Outlook data...")
    try:
        all_events = outlook_collector.get_calendar_events(
            start_date=start_date,
            end_date=end_date,
        )
        all_emails_received = outlook_collector.get_emails(
            start_date=start_date,
            end_date=end_date,
            folder="inbox",
        )
        all_emails_sent = outlook_collector.get_sent_emails(
            start_date=start_date,
            end_date=end_date,
        )
        print(f"  Found {len(all_events)} events, {len(all_emails_received)} received emails, {len(all_emails_sent)} sent emails")
    except Exception as e:
        print(f"  ERROR: Failed to fetch Outlook data: {e}")
        all_events = []
        all_emails_received = []
        all_emails_sent = []

    # Collect data for each client
    print("\nCollecting data for each client...")
    clients_data = []
    report_gen = ReportGenerator()

    for client in clients:
        client_name = client["name"]
        print(f"  Processing: {client_name}")

        # Filter Outlook data for this client
        client_events = outlook_collector.filter_by_client(all_events, client_name)
        client_emails_received = outlook_collector.filter_by_client(all_emails_received, client_name)
        client_emails_sent = outlook_collector.filter_by_client(all_emails_sent, client_name)

        outlook_data = {
            "events": client_events,
            "emails_received": client_emails_received,
            "emails_sent": client_emails_sent,
        }

        # Salesforce data
        salesforce_data = {}
        if salesforce_collector:
            try:
                salesforce_data = salesforce_collector.get_client_summary(
                    client_name=client_name,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as e:
                print(f"    Warning: Salesforce error for {client_name}: {e}")

        # Datadog data
        datadog_data = {}
        if datadog_collector:
            client_tag = f"client:{client_name.lower().replace(' ', '-')}"
            try:
                datadog_data = datadog_collector.get_client_usage(
                    client_tag=client_tag,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as e:
                print(f"    Warning: Datadog error for {client_name}: {e}")

        # Jira data
        jira_data = {}
        if jira_collector:
            try:
                jira_data = jira_collector.get_client_summary(
                    client_name=client_name,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as e:
                print(f"    Warning: Jira error for {client_name}: {e}")

        # Aggregate data
        client_summary = report_gen.aggregate_client_data(
            client_name=client_name,
            outlook_data=outlook_data,
            salesforce_data=salesforce_data,
            datadog_data=datadog_data,
            jira_data=jira_data,
        )

        clients_data.append(client_summary)

    # Generate report
    print("\nGenerating report...")
    html_report = report_gen.generate_report(
        clients_data=clients_data,
        start_date=start_date,
        end_date=end_date,
        include_inactive=False,
    )
    text_report = report_gen.generate_plain_text(
        clients_data=clients_data,
        start_date=start_date,
        end_date=end_date,
    )

    # Send email
    print("\nSending email...")
    subject = f"Weekly Client Summary - {start_date.strftime('%b %d')} to {end_date.strftime('%b %d, %Y')}"

    success = outlook_collector.send_email(
        to=recipient_email,
        subject=subject,
        html_body=html_report,
    )

    if success:
        print(f"\nEmail sent to {recipient_email}")
        print("\n" + "=" * 60)
        print("Report generation and delivery complete!")
    else:
        print("\nReport generated but email delivery failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
