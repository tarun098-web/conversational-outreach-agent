# Architecture

## Runtime path

The application is deliberately event-driven. Starting FastAPI creates provider
clients and serves HTTP; it does not schedule an AI loop. Work begins only when
Gmail Pub/Sub calls the webhook, a caller posts a normalized inbound message, a
reviewer requests regeneration, or an operator runs evaluation explicitly.

```mermaid
flowchart TD
  Gmail[Gmail push notification] --> Sync[History synchronizer]
  API[Normalized inbound API] --> Dedup
  Sync --> Dedup[External-ID deduplication]
  Dedup --> State[Supabase conversation state]
  State --> Knowledge[Approved knowledge retrieval]
  Knowledge --> Fast[Fast model: intent + risk]
  Fast --> Smart[Smart model: grounded draft + action proposal]
  Smart --> Policy[Deterministic policy and Pydantic validation]
  Policy --> Approval[Human approval dashboard]
  Approval --> Action[Approved action executor]
  Action --> Reply[Gmail thread reply]
  Reply --> Audit[State, audit and feedback]
  Audit --> Eval[Golden regression evaluation]
```

## Trust boundaries

1. Email text is always untrusted data and never placed in the system role.
2. Model output is a proposal and must pass Pydantic and policy validation.
3. Draft approval is claimed atomically before side effects, preventing two
   reviewers from sending the same draft.
4. The action executor accepts only enumerated actions and validated arguments.
5. Gmail and Supabase credentials remain server-side.

## Providers

The domain and service layers depend on protocols rather than SDKs. `mock`
providers make local demos and CI deterministic and free. `groq`, `gmail` and
`supabase` adapters activate through environment variables without changing the
workflow engine.

