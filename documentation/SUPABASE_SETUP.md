# Supabase setup

1. Create a Supabase project.
2. Open the SQL editor and run `database/migrations/001_initial.sql`.
3. Put `SUPABASE_URL` and a server-side key in `.env`.
4. Set `STORAGE_PROVIDER=supabase`.

All tables have row-level security enabled and the migration intentionally
creates no anonymous browser policies. The FastAPI backend should use a protected
service-role key. Do not expose that key to the dashboard or client JavaScript.

The knowledge table uses Postgres full-text search. Vector embeddings can be
added later without changing the repository contract.

