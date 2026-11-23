-- Owner-controlled in-app notification categories. Default preserves current delivery.
ALTER TABLE public.profiles
 ADD COLUMN notify_friends boolean NOT NULL DEFAULT true,
 ADD COLUMN notify_santa boolean NOT NULL DEFAULT true,
 ADD COLUMN notify_gifts boolean NOT NULL DEFAULT true,
 ADD COLUMN notify_system boolean NOT NULL DEFAULT true;
-- profiles remains backend-only under existing RLS/GRANT configuration.
