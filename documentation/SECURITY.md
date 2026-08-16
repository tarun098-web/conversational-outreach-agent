# Security model

- Emails are untrusted input and may contain prompt injection.
- Opt-outs are detected deterministically before any model call.
- Duplicate Gmail message IDs are rejected before model calls or side effects.
- Suppressed contacts cannot re-enter automated processing.
- The model can propose only enumerated actions; it cannot execute code or APIs.
- Actions and replies require human approval and an atomic draft claim.
- Pricing, legal, security and unsupported factual claims receive warnings or
  escalation.
- OAuth tokens, Groq keys and Supabase service keys are excluded from Git.
- Production deployments must terminate TLS, authenticate dashboard users,
  verify Google-signed Pub/Sub identities, rotate secrets and define retention.

The query-token check included for the demo is an additional shared secret, not
a substitute for verifying Google Cloud Pub/Sub OIDC tokens in production.

