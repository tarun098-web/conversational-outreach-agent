begin;

create extension if not exists pgcrypto;

create table if not exists contacts (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  name text,
  company text,
  timezone text,
  opted_out boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists conversations (
  id uuid primary key default gen_random_uuid(),
  contact_id uuid not null references contacts(id) on delete cascade,
  gmail_thread_id text unique,
  subject text not null,
  stage text not null default 'new',
  last_message_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  external_id text not null unique,
  direction text not null check (direction in ('inbound', 'outbound')),
  sender text not null,
  recipients jsonb not null default '[]'::jsonb,
  subject text not null,
  body_text text not null,
  gmail_thread_id text,
  in_reply_to text,
  raw_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  content text not null,
  source text not null,
  similarity double precision not null default 1,
  search_vector tsvector generated always as
    (setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
     setweight(to_tsvector('english', coalesce(content, '')), 'B')) stored,
  created_at timestamptz not null default now()
);
create index if not exists knowledge_documents_search_idx
  on knowledge_documents using gin(search_vector);

create table if not exists draft_responses (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  inbound_message_id uuid not null references messages(id) on delete cascade,
  body text not null,
  analysis jsonb not null,
  action jsonb not null,
  evidence jsonb not null default '[]'::jsonb,
  warnings text[] not null default '{}',
  status text not null default 'awaiting_approval',
  model_name text not null,
  prompt_version text not null default 'v1',
  reviewer_note text,
  human_edited_body text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists actions (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  draft_id uuid not null references draft_responses(id) on delete cascade,
  type text not null,
  arguments jsonb not null default '{}'::jsonb,
  status text not null default 'proposed',
  result jsonb not null default '{}'::jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists workflow_events (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  step text not null,
  status text not null default 'completed',
  detail text not null,
  metadata jsonb not null default '{}'::jsonb,
  correlation_id text not null,
  created_at timestamptz not null default now()
);
create index if not exists workflow_events_conversation_created_idx
  on workflow_events(conversation_id, created_at);

create table if not exists mailbox_sync_state (
  mailbox text primary key,
  history_id text not null,
  updated_at timestamptz not null default now()
);

create table if not exists evaluation_runs (
  id uuid primary key default gen_random_uuid(),
  model_name text not null,
  prompt_version text not null,
  dataset_version text not null,
  metrics jsonb not null,
  passed boolean not null,
  created_at timestamptz not null default now()
);

alter table contacts enable row level security;
alter table conversations enable row level security;
alter table messages enable row level security;
alter table knowledge_documents enable row level security;
alter table draft_responses enable row level security;
alter table actions enable row level security;
alter table workflow_events enable row level security;
alter table mailbox_sync_state enable row level security;
alter table evaluation_runs enable row level security;

-- The backend should use a protected server-side service-role key. No public
-- policies are created, so browser clients cannot access outreach data directly.

insert into knowledge_documents (title, content, source)
values
  ('Discovery meeting policy', 'Qualified prospects may request a 30-minute discovery meeting.', 'seed'),
  ('Pricing policy', 'Pricing is tailored after discovery. Never invent or quote an unapproved price.', 'seed')
on conflict do nothing;

commit;

