"""
One-time script to get a Microsoft Graph refresh token.

Run this locally, sign in with your Microsoft account, and copy the
refresh token to your GitHub secrets.

Usage:
    python scripts/get_refresh_token.py
"""

import http.server
import urllib.parse
import webbrowser
import requests
import sys

# Azure AD App Configuration
CLIENT_ID = "d679d9d3-5dd1-454f-b3dd-53f3a9b909c3"
TENANT_ID = "1cdfbb46-a98c-40e1-9173-60fda279a56c"
REDIRECT_URI = "http://localhost:8000/callback"

# Scopes needed for the app
SCOPES = [
    "offline_access",  # Required to get refresh token
    "Calendars.Read",
    "Mail.Read",
    "Mail.Send",
    "Files.Read",
    "User.Read",
]

# Global to store the auth code
auth_code = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handle the OAuth callback."""

    def do_GET(self):
        global auth_code

        # Parse the callback URL
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        elif "error" in params:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error = params.get("error", ["Unknown"])[0]
            error_desc = params.get("error_description", ["No description"])[0]
            self.wfile.write(f"""
                <html>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Authentication Failed</h1>
                    <p>Error: {error}</p>
                    <p>{error_desc}</p>
                </body>
                </html>
            """.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logging


def get_auth_url():
    """Build the authorization URL."""
    base_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize"
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "response_mode": "query",
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code):
    """Exchange authorization code for tokens."""
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"

    data = {
        "client_id": CLIENT_ID,
        "scope": " ".join(SCOPES),
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    response = requests.post(token_url, data=data)
    return response.json()


def main():
    global auth_code

    print("=" * 60)
    print("Microsoft Graph Refresh Token Generator")
    print("=" * 60)
    print()
    print("This will open your browser to sign in with Microsoft.")
    print("After signing in, the refresh token will be displayed here.")
    print()

    # Start local server
    server = http.server.HTTPServer(("localhost", 8000), CallbackHandler)

    # Open browser to auth URL
    auth_url = get_auth_url()
    print("Opening browser for authentication...")
    print()
    webbrowser.open(auth_url)

    # Wait for callback
    print("Waiting for authentication callback...")
    while auth_code is None:
        server.handle_request()

    server.server_close()
    print()
    print("Authorization code received. Exchanging for tokens...")
    print()

    # Exchange code for tokens
    tokens = exchange_code_for_tokens(auth_code)

    if "error" in tokens:
        print(f"ERROR: {tokens.get('error')}")
        print(f"Description: {tokens.get('error_description')}")
        sys.exit(1)

    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    if not refresh_token:
        print("ERROR: No refresh token received.")
        print("Make sure 'offline_access' scope is consented.")
        sys.exit(1)

    # Verify the token works
    print("Verifying token...")
    headers = {"Authorization": f"Bearer {access_token}"}
    me = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)

    if me.status_code == 200:
        user = me.json()
        print(f"Authenticated as: {user.get('displayName')} ({user.get('mail')})")
    else:
        print(f"Warning: Could not verify user: {me.status_code}")

    print()
    print("=" * 60)
    print("SUCCESS! Here is your refresh token:")
    print("=" * 60)
    print()
    print(refresh_token)
    print()
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Copy the refresh token above")
    print("2. Go to your GitHub repo → Settings → Secrets → Actions")
    print("3. Add a new secret named: MS_REFRESH_TOKEN")
    print("4. Paste the refresh token as the value")
    print()
    print("Note: This token is tied to YOUR Microsoft account.")
    print("Each user who wants their own report needs to run this script")
    print("and use their own refresh token.")
    print()


if __name__ == "__main__":
    main()
