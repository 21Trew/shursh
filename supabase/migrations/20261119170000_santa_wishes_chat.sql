-- This migration only adds columns and one table, never deletes user data.
-- A locked-down, in-database rollback snapshot protects pre-existing
-- participant wishes during the rollout (NOT a replacement for an offsite backup).
CREATE SCHEMA IF NOT EXISTS shursh_recovery;
REVOKE ALL ON SCHEMA shursh_recovery FROM PUBLIC, anon, authenticated, shursh_backend;
CREATE TABLE shursh_recovery.participant_wishes_before_santa_v2 AS
  SELECT * FROM public.participant_wishes;
REVOKE ALL ON TABLE shursh_recovery.participant_wishes_before_santa_v2
  FROM PUBLIC, anon, authenticated, shursh_backend;

-- Add richer wishes and private, server-authorized Santa chats.
-- Data migration is additive; apply only through an approved DB release.
ALTER TABLE public.participant_wishes
  ADD COLUMN description text NOT NULL DEFAULT '' CHECK (char_length(description)<=800),
  ADD COLUMN wanted text NOT NULL DEFAULT '' CHECK (char_length(wanted)<=500),
  ADD COLUMN unwanted text NOT NULL DEFAULT '' CHECK (char_length(unwanted)<=500),
  ADD COLUMN price_cents bigint CHECK (price_cents BETWEEN 0 AND 10000000000),
  ADD COLUMN currency text NOT NULL DEFAULT 'RUB' CHECK (currency IN ('RUB','EUR','USD')),
  ADD COLUMN shop_url text CHECK (shop_url IS NULL OR (char_length(shop_url)<=2000 AND shop_url ~ '^https?://')),
  ADD COLUMN image_data text CHECK (image_data IS NULL OR char_length(image_data)<=350000);

CREATE TABLE public.santa_messages(
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id bigint NOT NULL REFERENCES public.santa_events(id) ON DELETE CASCADE,
  sender_id bigint NOT NULL,
  room text NOT NULL CHECK (room IN ('general','pair')),
  pair_giver_id bigint,
  message text NOT NULL CHECK (char_length(message) BETWEEN 1 AND 500),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (event_id,sender_id) REFERENCES public.participants(event_id,id) ON DELETE CASCADE,
  FOREIGN KEY (event_id,pair_giver_id) REFERENCES public.participants(event_id,id) ON DELETE CASCADE,
  CHECK ((room='general' AND pair_giver_id IS NULL) OR
         (room='pair' AND pair_giver_id IS NOT NULL))
);
CREATE INDEX santa_messages_room_idx ON public.santa_messages(event_id,room,pair_giver_id,id DESC);
ALTER TABLE public.santa_messages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.santa_messages FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.santa_messages TO shursh_backend;
GRANT USAGE,SELECT ON SEQUENCE public.santa_messages_id_seq TO shursh_backend;
CREATE POLICY shursh_backend_only ON public.santa_messages
 FOR ALL TO shursh_backend USING(true) WITH CHECK(true);
