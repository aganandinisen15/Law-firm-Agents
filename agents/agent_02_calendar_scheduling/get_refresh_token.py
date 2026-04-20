from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.compose",
]

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": "",
            "client_secret": "",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    },
    SCOPES
)

creds = flow.run_local_server(
    port=0,
    access_type="offline",
    prompt="consent"
)

print("REFRESH TOKEN:")
print(creds.refresh_token)