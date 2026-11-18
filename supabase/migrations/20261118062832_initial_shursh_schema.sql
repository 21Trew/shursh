-- Shursh: server-only persistent MVP data model.
-- Browser roles have no table privileges. Supabase Auth is the identity provider.
-- Public link operations will be authorized by the backend, never by direct table access.
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  name text not null check (char_length(btrim(name)) between 1 and 140),
  created_at timestamptz not null default now()
);

create table public.wishlists (
  id bigint generated always as identity primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(btrim(title)) between 1 and 140),
  description text not null default '' check (char_length(description) <= 2000),
  occasion text not null default 'Просто так',
  theme text not null default 'peach',
  visibility text not null default 'link' check (visibility in ('link', 'private')),
  share_key text not null unique check (char_length(share_key) between 32 and 128),
  created_at timestamptz not null default now()
);
create index wishlists_owner_idx on public.wishlists(owner_id);

create table public.wishes (
  id bigint generated always as identity primary key,
  list_id bigint not null references public.wishlists(id) on delete cascade,
  title text not null check (char_length(btrim(title)) between 1 and 140),
  description text not null default '' check (char_length(description) <= 2000),
  price_cents bigint check (price_cents between 0 and 10000000000),
  currency text not null default 'RUB' check (currency ~ '^[A-Z]{3}$'),
  priority text not null default 'nice',
  kind text not null default 'item' check (kind in ('item', 'experience')),
  shop_url text check (shop_url is null or (char_length(shop_url) <= 2000 and shop_url ~ '^https?://')),
  image_path text,
  created_at timestamptz not null default now()
);
create index wishes_list_idx on public.wishes(list_id);

create table public.reservations (
  id bigint generated always as identity primary key,
  wish_id bigint not null references public.wishes(id) on delete cascade,
  guest_name text not null check (char_length(btrim(guest_name)) between 1 and 140),
  manage_hash text not null unique check (manage_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  cancelled_at timestamptz check (cancelled_at is null or cancelled_at >= created_at)
);
create unique index reservations_one_active on public.reservations(wish_id) where cancelled_at is null;
create index reservations_wish_idx on public.reservations(wish_id);

create table public.santa_events (
  id bigint generated always as identity primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(btrim(title)) between 1 and 140),
  description text not null default '' check (char_length(description) <= 2000),
  exchange_date date,
  budget_cents bigint check (budget_cents between 0 and 10000000000),
  currency text not null default 'RUB' check (currency ~ '^[A-Z]{3}$'),
  rules text not null default '' check (char_length(rules) <= 4000),
  invite_key text not null unique check (char_length(invite_key) between 32 and 128),
  status text not null default 'open' check (status in ('open', 'drawn')),
  created_at timestamptz not null default now()
);
create index santa_events_owner_idx on public.santa_events(owner_id);

create table public.participants (
  id bigint generated always as identity primary key,
  event_id bigint not null references public.santa_events(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  name text not null check (char_length(btrim(name)) between 1 and 140),
  access_hash text unique check (access_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  unique (event_id, id),
  unique (event_id, user_id)
);
create index participants_user_idx on public.participants(user_id);

create table public.participant_wishes (
  id bigint generated always as identity primary key,
  participant_id bigint not null references public.participants(id) on delete cascade,
  title text not null check (char_length(btrim(title)) between 1 and 140),
  created_at timestamptz not null default now()
);
create index participant_wishes_participant_idx on public.participant_wishes(participant_id);

create table public.exclusions (
  event_id bigint not null references public.santa_events(id) on delete cascade,
  giver_id bigint not null,
  receiver_id bigint not null,
  primary key (event_id, giver_id, receiver_id),
  foreign key (event_id, giver_id) references public.participants(event_id, id) on delete cascade,
  foreign key (event_id, receiver_id) references public.participants(event_id, id) on delete cascade,
  check (giver_id <> receiver_id)
);
create index exclusions_receiver_idx on public.exclusions(event_id, receiver_id);

create table public.assignments (
  event_id bigint not null references public.santa_events(id) on delete cascade,
  giver_id bigint not null,
  receiver_id bigint not null,
  revealed_at timestamptz,
  primary key (event_id, giver_id),
  unique (event_id, receiver_id),
  foreign key (event_id, giver_id) references public.participants(event_id, id) on delete cascade,
  foreign key (event_id, receiver_id) references public.participants(event_id, id) on delete cascade,
  check (giver_id <> receiver_id)
);

-- Only trusted backend routes can access application tables.
-- The owner/guest-specific projection and workflow authorization are implemented separately.
do $$
declare t text;
begin
  foreach t in array array['profiles','wishlists','wishes','reservations','santa_events','participants','participant_wishes','exclusions','assignments'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all privileges on table public.%I from public, anon, authenticated', t);
    execute format('grant select, insert, update, delete on table public.%I to service_role', t);
  end loop;
end
$$;
do $$
declare s record;
begin
  for s in select sequence_name from information_schema.sequences
    where sequence_schema = 'public'
    and sequence_name in ('wishlists_id_seq','wishes_id_seq','reservations_id_seq','santa_events_id_seq','participants_id_seq','participant_wishes_id_seq')
  loop
    execute format('revoke all privileges on sequence public.%I from public, anon, authenticated',s.sequence_name);
    execute format('grant usage, select on sequence public.%I to service_role',s.sequence_name);
  end loop;
end
$$;
