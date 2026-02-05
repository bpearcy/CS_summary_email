"""
Main orchestrator - coordinates data collection and report generation.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional
import requests
import msal

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


def send_email_via_graph(
    client_id: str,
    client_secret: str,
    tenant_id: str,
    recipient: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> bool:
    """Send email using Microsoft Graph API."""
    # Get access token
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )

    if "access_token" not in result:
        print(f"Failed to get access token: {result.get('error_description')}")
        return False

    # Send email
    url = f"https://graph.microsoft.com/v1.0/users/{recipient}/sendMail"
    headers = {
        "Authorization": f"Bearer {result['access_token']}",
        "Content-Type": "application/json",
    }

    email_data = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body,
            },
            "toRecipients": [
                {"emailAddress": {"address": recipient}}
            ],
        },
        "saveToSentItems": True,
    }

    response = requests.post(url, headers=headers, json=email_data)

    if response.status_code == 202:
        print(f"Email sent successfully to {recipient}")
        return True
    else:
        print(f"Failed to send email: {response.status_code} - {response.text}")
        return False


def main():
    """Main entry point."""
    print("Starting Weekly Client Summary Report Generation...")
    print("=" * 60)

    # Get configuration from environment
    ms_client_id = os.environ.get("MS_CLIENT_ID")
    ms_client_secret = os.environ.get("MS_CLIENT_SECRET")
    ms_tenant_id = os.environ.get("MS_TENANT_ID")
    excel_file_id = os.environ.get("EXCEL_FILE_ID")
    recipient = os.environ.get("REPORT_RECIPIENT")

    if not all([ms_client_id, ms_client_secret, ms_tenant_id, recipient]):
        print("ERROR: Missing required Microsoft configuration")
        sys.exit(1)

    # Initialize collectors
    print("\nInitializing collectors...")

    excel_collector = ExcelCollector(
        client_id=ms_client_id,
        client_secret=ms_client_secret,
        tenant_id=ms_tenant_id,
        file_id=excel_file_id,
    )

    outlook_collector = OutlookCollector(
        client_id=ms_client_id,
        client_secret=ms_client_secret,
        tenant_id=ms_tenant_id,
    )

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
    if os.environ.get("JIRA_URL"):
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
        # Fallback to empty list or exit
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

    for client in clients:
        client_name = client["name"]
        print(f"  Processing: {client_name}")

        # Filter Outlook data for this client
        # TODO: Add email domain mapping to spreadsheet
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
            # TODO: Add datadog tag mapping to spreadsheet
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
            # TODO: Add Jira label mapping to spreadsheet
            client_label = f"client-{client_name.lower().replace(' ', '-')}"
            try:
                jira_data = jira_collector.get_client_summary(
                    client_label=client_label,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as e:
                print(f"    Warning: Jira error for {client_name}: {e}")

        # Aggregate data
        report_gen = ReportGenerator()
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
    report_gen = ReportGenerator()
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

    success = send_email_via_graph(
        client_id=ms_client_id,
        client_secret=ms_client_secret,
        tenant_id=ms_tenant_id,
        recipient=recipient,
        subject=subject,
        html_body=html_report,
        text_body=text_report,
    )

    if success:
        print("\n" + "=" * 60)
        print("Report generation and delivery complete!")
    else:
        print("\nReport generated but email delivery failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
