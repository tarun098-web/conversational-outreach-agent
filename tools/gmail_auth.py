"""Create a Gmail OAuth token inside the project's D:-local .runtime folder."""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = PROJECT_ROOT / ".runtime" / "credentials.json"
TOKEN = PROJECT_ROOT / ".runtime" / "token.json"


def main() -> None:
    if not CREDENTIALS.exists():
        raise SystemExit(f"Missing OAuth client credentials: {CREDENTIALS}")
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
    credentials = flow.run_local_server(port=0)
    TOKEN.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Gmail OAuth token saved to {TOKEN}")


if __name__ == "__main__":
    main()
