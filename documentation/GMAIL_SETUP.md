# Gmail setup

1. Create a Google Cloud project and enable the Gmail API.
2. Configure an OAuth consent screen and create a Desktop OAuth client.
3. Save the downloaded client JSON as `.runtime/credentials.json`.
4. From the project virtual environment run `python tools/gmail_auth.py`.
5. Set `EMAIL_PROVIDER=gmail`.

For push delivery, create a Google Cloud Pub/Sub topic, grant Gmail permission
to publish to it, configure a push subscription pointing at
`https://YOUR_HOST/api/v1/webhooks/gmail?token=YOUR_RANDOM_TOKEN`, and set the
same value in `GMAIL_PUBSUB_VERIFICATION_TOKEN`.

Call Gmail `users.watch` for the mailbox and topic. Gmail watch registrations
expire and should be renewed by infrastructure automation; renewal does not call
the language model. The first notification establishes a history cursor without
replaying an entire mailbox.

Never commit OAuth client credentials or `.runtime/token.json`.

