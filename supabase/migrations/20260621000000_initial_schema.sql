-- Lengua initial schema
-- Run via: supabase db push (local) or Alembic (backend)
-- This file handles Supabase-specific concerns: RLS policies, auth.users references.
-- The table DDL itself will be owned by Alembic once the FastAPI backend is built.
-- For now this is a reference + can be applied directly to a fresh local DB.

-- ── Tables ────────────────────────────────────────────────────────────────────

create table if not exists profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  plan       text not null default 'free',
  created_at timestamptz not null default now()
);

create table if not exists languages (
  id         bigint generated always as identity primary key,
  user_id    uuid not null references profiles(id) on delete cascade,
  name       text not null,
  code       text,
  vowelized  boolean not null default false,
  created_at timestamptz not null default now(),
  unique (user_id, name)
);

create table if not exists cards (
  id                bigint generated always as identity primary key,
  user_id           uuid not null references profiles(id) on delete cascade,
  language_id       bigint not null references languages(id) on delete cascade,
  front             text not null,
  back              text not null,
  used_words        jsonb,
  direction         text,        -- 'recognition' | 'production'
  word_explanations jsonb,
  gen_level         real,
  saved             boolean not null default false,
  fsrs_state        jsonb,       -- fsrs.Card serialized
  due               timestamptz,
  created_at        timestamptz not null default now()
);
create index if not exists cards_user_lang_due on cards (user_id, language_id, saved, due);

create table if not exists reviews (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references profiles(id) on delete cascade,
  card_id     bigint not null references cards(id) on delete cascade,
  rating      smallint not null,   -- 1=Again 2=Hard 3=Good 4=Easy
  reviewed_at timestamptz not null default now()
);

create table if not exists proficiency (
  user_id     uuid not null references profiles(id) on delete cascade,
  language_id bigint not null references languages(id) on delete cascade,
  score       real not null default 0.0,
  updated_at  timestamptz not null default now(),
  primary key (user_id, language_id)
);

create table if not exists user_settings (
  user_id uuid not null references profiles(id) on delete cascade,
  key     text not null,
  value   text,
  primary key (user_id, key)
);

-- LLM usage tracking (provider-agnostic; table name is historical)
create table if not exists llm_usage (
  user_id uuid not null references profiles(id) on delete cascade,
  day     date not null,
  kind    text not null,          -- 'generate' | 'discover' | 'explain'
  count   int  not null default 0,
  primary key (user_id, day, kind)
);

-- Project-wide daily budget kill-switch
create table if not exists llm_budget (
  day   date primary key,
  count int not null default 0
);

-- ── Row-Level Security ────────────────────────────────────────────────────────

alter table profiles      enable row level security;
alter table languages     enable row level security;
alter table cards         enable row level security;
alter table reviews       enable row level security;
alter table proficiency   enable row level security;
alter table user_settings enable row level security;
alter table llm_usage     enable row level security;
-- llm_budget is global (no RLS — only service_role writes it)

create policy profiles_owner      on profiles      using (id = auth.uid())               with check (id = auth.uid());
create policy languages_owner     on languages     using (user_id = auth.uid())           with check (user_id = auth.uid());
create policy cards_owner         on cards         using (user_id = auth.uid())           with check (user_id = auth.uid());
create policy reviews_owner       on reviews       using (user_id = auth.uid())           with check (user_id = auth.uid());
create policy proficiency_owner   on proficiency   using (user_id = auth.uid())           with check (user_id = auth.uid());
create policy user_settings_owner on user_settings using (user_id = auth.uid())           with check (user_id = auth.uid());
create policy llm_usage_owner     on llm_usage     using (user_id = auth.uid())           with check (user_id = auth.uid());

-- ── Auto-create profile on signup ─────────────────────────────────────────────

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id) values (new.id);
  return new;
end;
$$;

create or replace trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
