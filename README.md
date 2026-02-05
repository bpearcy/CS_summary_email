# Weekly Client Summary Email

Automated weekly email summarizing all client interactions across multiple systems.

## Data Sources

- **Outlook** - Calendar meetings and email exchanges
- **Excel Online** - Client list (source of truth)
- **Salesforce** - Activities, tasks, and opportunities
- **Datadog** - Usage metrics and monitor status
- **Jira** - Tickets and document submissions

## Setup

### 1. Azure App Registration (Microsoft Graph)

Create an Azure AD app for Microsoft Graph access:

1. Go to [Azure Portal](https://portal.azure.com) > Azure Active Directory > App registrations
2. Click "New registration"
3. Name: `CS Summary Email`
4. Supported account types: Single tenant
5. After creation, go to "API permissions" and add:
   - `Mail.Read` - Read user mail
   - `Mail.Send` - Send mail as user
   - `Calendars.Read` - Read user calendars
   - `Files.Read.All` - Read files (for Excel)
6. Click "Grant admin consent"
7. Go to "Certificates & secrets" > "New client secret"
8. Copy the secret value (you'll need this)

### 2. Get Excel File ID

1. Open your Excel file in OneDrive/SharePoint
2. The URL will look like: `https://company.sharepoint.com/.../Clients%20and%20Products.xlsx?...`
3. Use Graph Explorer to get the file ID, or extract from the URL

### 3. Salesforce Connected App

1. Go to Setup > App Manager > New Connected App
2. Enable OAuth Settings
3. Select scopes: `api`, `refresh_token`
4. Get Consumer Key and Consumer Secret

### 4. Datadog API Keys

1. Go to Organization Settings > API Keys
2. Create new API key
3. Go to Organization Settings > Application Keys
4. Create new Application key

### 5. Jira API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Create new API token

### 6. GitHub Secrets

Add these secrets to your GitHub repository (Settings > Secrets > Actions):

| Secret | Description |
|--------|-------------|
| `MS_CLIENT_ID` | Azure AD App Client ID |
| `MS_CLIENT_SECRET` | Azure AD App Client Secret |
| `MS_TENANT_ID` | Azure AD Tenant ID |
| `EXCEL_FILE_ID` | OneDrive/SharePoint file ID for client spreadsheet |
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
| `REPORT_RECIPIENT` | Email address to receive the report |

## Spreadsheet Format

Your Excel spreadsheet should have these columns:

| Column | Description |
|--------|-------------|
| Client | Client name (required) |
| Data Location Requirements | Optional notes |
| Subcontractor Requirements | Optional notes |

Future enhancement: Add columns for email domains, Salesforce Account IDs, Datadog tags, and Jira labels.

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (or create .env file)
export MS_CLIENT_ID=...
export MS_CLIENT_SECRET=...
# ... etc

# Run
python src/main.py
```

## Schedule

The GitHub Action runs every Monday at 8 AM Eastern (13:00 UTC).

You can also trigger manually via Actions > Weekly Client Summary > Run workflow.

## Customization

### Adding Client Identifiers

To improve matching accuracy, add columns to your spreadsheet:

- `Email Domains` - Comma-separated domains (e.g., `acme.com, acme.io`)
- `Salesforce Account ID` - Direct SF Account ID
- `Datadog Tag` - Client tag in Datadog (e.g., `client:acme`)
- `Jira Label` - Label used in Jira (e.g., `client-acme`)

### Datadog Metrics

Edit `src/collectors/datadog.py` to customize which metrics are pulled for each client.

### Report Template

Modify `templates/email_template.html` to customize the email appearance.
