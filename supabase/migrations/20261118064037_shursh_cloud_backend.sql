-- Cloud backend: scoped application role; browser roles remain denied.
create role shursh_backend nologin noinherit;
grant shursh_backend to postgres;
grant usage on schema public to shursh_backend;

create table public.app_sessions (
 token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
 user_id uuid not null references auth.users(id) on delete cascade,
 email text not null check (char_length(email) <= 254),
 expires_at bigint not null,
 created_at timestamptz not null default now()
);
create index app_sessions_user_idx on public.app_sessions(user_id);
create index app_sessions_expiry_idx on public.app_sessions(expires_at);

-- Small private database-backed image store for the free MVP. Files are served
-- only through the API after checking the associated wishlist's visibility.
create table public.wish_images (
 path text primary key check (path ~ '^/uploads/[a-f0-9]{40}\.(jpg|png|webp)$'),
 list_id bigint not null references public.wishlists(id) on delete cascade,
 mime text not null check (mime in ('image/jpeg','image/png','image/webp')),
 content bytea not null check (octet_length(content) between 8 and 2000000),
 created_at timestamptz not null default now()
);
create index wish_images_list_idx on public.wish_images(list_id);

create table public.app_rate_limits (
 key_hash text primary key check (key_hash ~ '^[0-9a-f]{64}$'),
 bucket bigint not null,
 hits integer not null check (hits > 0)
);
create index app_rate_limits_bucket_idx on public.app_rate_limits(bucket);

do $$
declare t text;
begin
  foreach t in array array['profiles','wishlists','wishes','reservations','santa_events','participants','participant_wishes','exclusions','assignments','app_sessions','wish_images','app_rate_limits'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all privileges on table public.%I from public, anon, authenticated',t);
    execute format('grant select, insert, update, delete on table public.%I to shursh_backend',t);
    execute format('create policy shursh_backend_only on public.%I for all to shursh_backend using (true) with check (true)',t);
  end loop;
end $$;
grant usage, select on sequence public.wishlists_id_seq, public.wishes_id_seq,
 public.reservations_id_seq, public.santa_events_id_seq, public.participants_id_seq,
 public.participant_wishes_id_seq to shursh_backend;

-- Removing/replacing a wish deletes its old image. All mutations are in the
-- same transaction; list deletion also cascades to the image table.
create function public.shursh_cleanup_wish_image() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  if old.image_path is not null then
    if tg_op = 'DELETE' then
      delete from public.wish_images where path = old.image_path and list_id = old.list_id;
    elsif old.image_path is distinct from new.image_path then
      delete from public.wish_images where path = old.image_path and list_id = old.list_id;
    end if;
  end if;
  return null;
end $$;
revoke all on function public.shursh_cleanup_wish_image() from public, anon, authenticated;
grant execute on function public.shursh_cleanup_wish_image() to shursh_backend;
create trigger shursh_cleanup_wish_image after delete or update of image_path on public.wishes
for each row execute function public.shursh_cleanup_wish_image();
