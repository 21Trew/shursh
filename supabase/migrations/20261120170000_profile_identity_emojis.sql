-- Additive, private profile identity extension. No avatar uploads.
ALTER TABLE public.profiles
 ADD COLUMN handle text CHECK (handle IS NULL OR handle ~ '^[a-z][a-z0-9_]{2,19}$'),
 ADD COLUMN avatar_emoji text NOT NULL DEFAULT '🎁' CHECK (avatar_emoji IN ('🎁','🎄','🐱','🦊','🐻','🐼','🐸','🦄','🐰','🧸','✨','🌸','🌼','🌙','⭐','🎮','🎨','📚','🎵','🚀','☕','🍓','💚')),
 ADD COLUMN city text NOT NULL DEFAULT '' CHECK (char_length(city)<=60);
CREATE UNIQUE INDEX profiles_handle_unique_idx ON public.profiles (lower(handle)) WHERE handle IS NOT NULL;
-- Existing profile RLS stays enabled. No new client privileges.
