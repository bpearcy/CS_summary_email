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


def get_date_range() -> tuple[datetime, datetime]:
    """Get the date range for the report (Monday-Sunday of current week)."""
    today = datetime.utcnow().date()
    # Find Monday of this week (weekday() returns 0 for Monday)
    days_since_monday = today.weekday()
    monday = today - timedelta(days=days_since_monday)
    sunday = monday + timedelta(days=6)

    # Convert to datetime at start/end of day
    start_date = datetime.combine(monday, datetime.min.time())
    end_date = datetime.combine(sunday, datetime.max.time())

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

    # Get date range (Monday-Sunday of current week)
    start_date, end_date = get_date_range()
    print(f"\nReport period: {start_date.strftime('%Y-%m-%d')} (Mon) to {end_date.strftime('%Y-%m-%d')} (Sun)")

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
            import traceback
            traceback.print_exc()

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

    # Fallback: use Jira clients if Excel fails (no hardcoded list since we filter by status)
    FALLBACK_CLIENTS = []

    # Get client list from Excel spreadsheet (authoritative list)
    print("\nFetching client list from Excel...")
    all_client_names = []
    try:
        all_client_names = excel_collector.get_client_names()
        print(f"  Found {len(all_client_names)} clients in spreadsheet")
        for name in all_client_names[:5]:
            print(f"    - {name}")
        if len(all_client_names) > 5:
            print(f"    ... and {len(all_client_names) - 5} more")
    except Exception as e:
        print(f"  ERROR: Failed to fetch client list: {e}")
        import traceback
        traceback.print_exc()

    # Fall back to Jira clients if Excel fails or returns empty
    if not all_client_names:
        all_client_names = sorted(jira_by_client.keys())
        print(f"  Using Jira clients as fallback ({len(all_client_names)} clients)")

    # Build report for ALL clients
    print("\nBuilding report by client...")
    clients_data = []
    report_gen = ReportGenerator()

    for client_name in all_client_names:
        # Skip internal/demo clients
        if "demo" in client_name.lower() or "client success" in client_name.lower():
            continue

        # Get Jira tickets for this client (fuzzy match on client name)
        tickets = []
        for jira_client, jira_tickets in jira_by_client.items():
            if client_name.lower() in jira_client.lower() or jira_client.lower() in client_name.lower():
                tickets.extend(jira_tickets)

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

        # Get Outlook data for this client (fuzzy match)
        client_events = outlook_collector.filter_by_client(all_events, client_name)
        client_emails_received = outlook_collector.filter_by_client(all_emails_received, client_name)
        client_emails_sent = outlook_collector.filter_by_client(all_emails_sent, client_name)

        outlook_data = {
            "events": client_events,
            "emails_received": client_emails_received,
            "emails_sent": client_emails_sent,
        }

        # Datadog data placeholder (time on platform)
        datadog_data = {
            "time_on_platform": 0,  # TODO: Integrate with Datadog
        }

        # Aggregate data
        client_summary = report_gen.aggregate_client_data(
            client_name=client_name,
            outlook_data=outlook_data,
            salesforce_data={},
            datadog_data=datadog_data,
            jira_data=jira_data,
        )

        clients_data.append(client_summary)

        # Log summary for this client
        docs = len(tickets)
        emails = len(client_emails_received) + len(client_emails_sent)
        meetings = len(client_events)
        print(f"  {client_name}: {docs} docs, {emails} emails, {meetings} meetings")

    # Generate report
    print(f"\nGenerating report for {len(clients_data)} clients...")
    html_report = report_gen.generate_report(
        clients_data=clients_data,
        start_date=start_date,
        end_date=end_date,
        include_inactive=True,  # Show ALL clients
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
