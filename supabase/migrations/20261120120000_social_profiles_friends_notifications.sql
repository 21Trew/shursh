-- Shursh Social v1. Additive and backend-only; never apply to Production without approval.
-- Profile display settings: never expose emails in public profile responses.
ALTER TABLE public.profiles
 ADD COLUMN bio text NOT NULL DEFAULT '' CHECK (char_length(bio)<=500),
 ADD COLUMN discoverable boolean NOT NULL DEFAULT true;

CREATE TABLE public.friendships(
 user_low uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 user_high uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 requested_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','declined')),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_low,user_high),
 CHECK(user_low<user_high),
 CHECK(requested_by=user_low OR requested_by=user_high)
);
CREATE INDEX friendships_high_status_idx ON public.friendships(user_high,status);
CREATE INDEX friendships_low_status_idx ON public.friendships(user_low,status);

CREATE TABLE public.social_notifications(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 recipient_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 actor_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
 kind text NOT NULL CHECK(kind IN ('friend_request','friend_accept','wishlist_new','wish_new','reservation_anonymous',
        'santa_invitation','santa_joined','santa_drawn','wish_request')),
 message text NOT NULL CHECK(char_length(message) BETWEEN 1 AND 240),
 target_path text NOT NULL DEFAULT '/' CHECK(char_length(target_path) BETWEEN 1 AND 300 AND left(target_path,1)='/'),
 read_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX social_notifications_recipient_idx
 ON public.social_notifications(recipient_id,id DESC);
CREATE INDEX social_notifications_unread_idx
 ON public.social_notifications(recipient_id,id DESC) WHERE read_at IS NULL;

CREATE TABLE public.santa_friend_invitations(
 event_id bigint NOT NULL REFERENCES public.santa_events(id) ON DELETE CASCADE,
 invited_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 invited_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted')),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(event_id,invited_user_id),
 CHECK(invited_user_id<>invited_by)
);
CREATE INDEX santa_friend_invites_user_idx ON public.santa_friend_invitations(invited_user_id,status);

CREATE TABLE public.wish_friend_requests(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 wish_id bigint NOT NULL REFERENCES public.wishes(id) ON DELETE CASCADE,
 requester_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 friend_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined')),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(wish_id,friend_id),
 CHECK(requester_id<>friend_id)
);
CREATE INDEX wish_friend_requests_recipient_idx ON public.wish_friend_requests(friend_id,status);

-- No direct client CRUD: authorization is performed in WSGI backend.
DO $$
DECLARE tab text;
BEGIN
 FOREACH tab IN ARRAY ARRAY[
  'friendships','social_notifications','santa_friend_invitations','wish_friend_requests'
 ] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated',tab);
  EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO shursh_backend',tab);
  EXECUTE format(
    'CREATE POLICY shursh_backend_only ON public.%I FOR ALL TO shursh_backend USING (true) WITH CHECK (true)',tab);
 END LOOP;
END $$;
GRANT USAGE, SELECT ON SEQUENCE public.social_notifications_id_seq,
 public.wish_friend_requests_id_seq TO shursh_backend;
REVOKE ALL ON SEQUENCE public.social_notifications_id_seq,
 public.wish_friend_requests_id_seq FROM PUBLIC, anon, authenticated;
