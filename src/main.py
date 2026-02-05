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

    # Debug: Check which optional env vars are set
    print("\n  Debug - Environment variables:")
    print(f"    SF_USERNAME set: {bool(os.environ.get('SF_USERNAME'))}")
    print(f"    DD_API_KEY set: {bool(os.environ.get('DD_API_KEY'))}")
    print(f"    JIRA_API_TOKEN set: {bool(os.environ.get('JIRA_API_TOKEN'))}")
    print(f"    JIRA_USERNAME set: {bool(os.environ.get('JIRA_USERNAME'))}")
    print(f"    JIRA_URL set: {bool(os.environ.get('JIRA_URL'))}")

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
    else:
        print("  - Jira collector SKIPPED (no JIRA_API_TOKEN)")

    # Get date range
    start_date, end_date = get_date_range(7)
    print(f"\nReport period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # Fetch Jira data FIRST - grouped by client
    # This gives us the authoritative list of clients with activity
    print("\nFetching Jira PRODOPS tickets...")
    jira_by_client = {}
    if jira_collector:
        try:
            jira_by_client = jira_collector.get_all_client_tickets(
                start_date=start_date,
                end_date=end_date,
            )
            total_tickets = sum(len(tickets) for tickets in jira_by_client.values())
            print(f"  Found {total_tickets} tickets across {len(jira_by_client)} clients")
            for client, tickets in sorted(jira_by_client.items()):
                print(f"    - {client}: {len(tickets)} tickets")
        except Exception as e:
            print(f"  ERROR: Failed to fetch Jira data: {e}")

    # Fetch Outlook data (calendar events and emails)
    print("\nFetching Outlook data...")
    all_events = []
    all_emails_received = []
    all_emails_sent = []
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

    # Build client list from Jira data (clients with actual activity)
    # This ensures we report on clients that have PRODOPS tickets
    print("\nBuilding report by client...")
    clients_data = []
    report_gen = ReportGenerator()

    # Process each client that has Jira tickets
    for client_name in sorted(jira_by_client.keys()):
        # Skip internal/demo clients
        if "demo" in client_name.lower() or "client success" in client_name.lower():
            continue

        tickets = jira_by_client[client_name]
        print(f"  Processing: {client_name} ({len(tickets)} PRODOPS tickets)")

        # Count ticket stats
        new_tickets = [t for t in tickets if t.get("created", "")[:10] >= start_date.strftime("%Y-%m-%d")]
        resolved_tickets = [t for t in tickets if t.get("resolved")]

        # Group by status
        by_status = {}
        for t in tickets:
            status = t.get("status", "Unknown")
            by_status[status] = by_status.get(status, 0) + 1

        jira_data = {
            "client": client_name,
            "total_issues": len(tickets),
            "new_issues": len(new_tickets),
            "resolved_issues": len(resolved_tickets),
            "by_status": by_status,
            "by_type": {"Support": len(tickets)},
            "issues": tickets,
        }

        # Try to find Outlook data for this client (fuzzy match)
        client_events = outlook_collector.filter_by_client(all_events, client_name)
        client_emails_received = outlook_collector.filter_by_client(all_emails_received, client_name)
        client_emails_sent = outlook_collector.filter_by_client(all_emails_sent, client_name)

        outlook_data = {
            "events": client_events,
            "emails_received": client_emails_received,
            "emails_sent": client_emails_sent,
        }

        # Aggregate data
        client_summary = report_gen.aggregate_client_data(
            client_name=client_name,
            outlook_data=outlook_data,
            salesforce_data={},
            datadog_data={},
            jira_data=jira_data,
        )

        clients_data.append(client_summary)

    # Generate report
    print(f"\nGenerating report for {len(clients_data)} clients...")
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
