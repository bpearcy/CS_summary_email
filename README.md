# Weekly Client Summary Email

Automated weekly email summarizing all client interactions across multiple systems.

## Data Sources

- **Outlook** - Calendar meetings and email exchanges
- **Excel Online** - Client list (source of truth)
- **Salesforce** - Activities, tasks, and opportunities
- **Datadog** - Usage metrics and monitor status
- **Jira** - Tickets and document submissions

## Security Model

This app uses **delegated permissions** with a refresh token. This means:
- Each user runs a one-time setup to authenticate with their Microsoft account
- The app only has access to **that user's** mailbox, calendar, and OneDrive
- No access to other users' data in the organization

## Setup

### 1. Azure App Registration

The Azure AD app should already be configured. If setting up fresh:

1. Go to [Azure Portal](https://portal.azure.com) > Azure Active Directory > App registrations
2. Create new registration named `CS Weekly Summary`
3. Add **Delegated** permissions (not Application):
   - `Calendars.Read`
   - `Mail.Read`
   - `Mail.Send`
   - `Files.Read`
   - `User.Read`
   - `offline_access`
4. Add redirect URI: `http://localhost:8000/callback` (Web platform)
5. Grant admin consent

### 2. Get Your Refresh Token

Run the token script locally:

```bash
cd CS_summary_email
pip install requests
python scripts/get_refresh_token.py
```

This will:
1. Open your browser to sign in with Microsoft
2. Display a refresh token
3. Copy this token for the next step

### 3. Get Excel File ID

After running the token script, you can find your Excel file ID:

```bash
python -c "
from src.auth import TokenManager
from src.collectors.excel import ExcelCollector
import os
os.environ['MS_REFRESH_TOKEN'] = 'your-refresh-token-here'
tm = TokenManager()
ec = ExcelCollector(tm)
result = ec.find_file('Clients and Products.xlsx')
print(f'File ID: {result[\"id\"]}')"
```

### 4. Configure GitHub Secrets

Add these secrets to your GitHub repository (Settings > Secrets > Actions):

**Required:**

| Secret | Description |
|--------|-------------|
| `MS_CLIENT_ID` | Azure AD App Client ID: `d679d9d3-5dd1-454f-b3dd-53f3a9b909c3` |
| `MS_TENANT_ID` | Azure AD Tenant ID: `1cdfbb46-a98c-40e1-9173-60fda279a56c` |
| `MS_REFRESH_TOKEN` | Your personal refresh token from step 2 |
| `EXCEL_FILE_ID` | OneDrive file ID for client spreadsheet |

**Optional (for additional data sources):**

| Secret | Description |
|--------|-------------|
| `SF_USERNAME` | Salesforce username |
| `SF_PASSWORD` | Salesforce password |
| `SF_SECURITY_TOKEN` | Salesforce security token |
| `SF_DOMAIN` | `login` or `test` |
| `DD_API_KEY` | Datadog API key |
| `DD_APP_KEY` | Datadog Application key |
| `DD_SITE` | Datadog site (e.g., `datadoghq.com`) |
| `JIRA_URL` | Jira instance URL |
| `JIRA_USERNAME` | Jira username (email) |
| `JIRA_API_TOKEN` | Jira API token |

## Spreadsheet Format

Your Excel spreadsheet should have these columns:

| Column | Description |
|--------|-------------|
| Client | Client name (required) |
| Data Location Requirements | Optional notes |
| Subcontractor Requirements | Optional notes |

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MS_REFRESH_TOKEN="your-refresh-token"
export EXCEL_FILE_ID="your-file-id"

# Optionally set Jira credentials
export JIRA_URL="https://streetdiligence.atlassian.net"
export JIRA_USERNAME="your-email"
export JIRA_API_TOKEN="your-token"

# Run
python src/main.py
```

## Schedule

The GitHub Action runs every Monday at 8 AM Eastern (13:00 UTC).

You can also trigger manually via Actions > Weekly Client Summary > Run workflow.

## Multi-User Setup

Each person who wants their own weekly summary needs to:

1. Run `python scripts/get_refresh_token.py` locally
2. Sign in with their Microsoft account
3. Add their personal `MS_REFRESH_TOKEN` to their own fork/branch

The token is tied to the individual user and only grants access to their data.

## Customization

### Report Template

Modify `templates/email_template.html` to customize the email appearance.

### Datadog Metrics

Edit `src/collectors/datadog.py` to customize which metrics are pulled for each client.
