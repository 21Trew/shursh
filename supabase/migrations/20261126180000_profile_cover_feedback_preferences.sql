-- Profile visibility, wishlist covers and feedback preferences.
-- Existing RLS policies and table grants remain in force.
ALTER TABLE public.profiles
 ADD COLUMN show_last_name boolean,
 ADD COLUMN show_patronymic boolean;
UPDATE public.profiles SET show_last_name=show_full_name,show_patronymic=show_full_name;
ALTER TABLE public.profiles
 ALTER COLUMN show_last_name SET DEFAULT false,
 ALTER COLUMN show_last_name SET NOT NULL,
 ALTER COLUMN show_patronymic SET DEFAULT false,
 ALTER COLUMN show_patronymic SET NOT NULL;
-- Preserve existing underscore nicknames; the API prevents assigning new ones.
ALTER TABLE public.profiles DROP CONSTRAINT profiles_handle_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_handle_check
 CHECK (handle IS NULL OR handle ~ '^[a-z0-9][a-z0-9_]{2,19}$');
ALTER TABLE public.wishlists ADD COLUMN cover_path text
 CHECK (cover_path IS NULL OR cover_path ~ '^/uploads/[a-f0-9]{40}\.(jpg|png|webp)$');
ALTER TABLE public.developer_feedback
 ADD COLUMN reply_email boolean NOT NULL DEFAULT true,
 ADD COLUMN notify_site boolean NOT NULL DEFAULT false,
 ADD COLUMN author_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
 ADD COLUMN source_route text NOT NULL DEFAULT 'other' CHECK (char_length(source_route)<=80),
 ADD COLUMN site_notified boolean NOT NULL DEFAULT false;
ALTER TABLE public.developer_feedback DROP CONSTRAINT developer_feedback_topic_check;
ALTER TABLE public.developer_feedback ADD CONSTRAINT developer_feedback_topic_check
 CHECK (topic IN ('idea','bug','question','other','thanks'));
ALTER TABLE public.social_notifications DROP CONSTRAINT social_notifications_kind_check;
ALTER TABLE public.social_notifications ADD CONSTRAINT social_notifications_kind_check
 CHECK (kind IN ('friend_request','friend_accept','wishlist_new','wish_new','reservation_anonymous','santa_invitation','santa_joined','santa_drawn','wish_request','feedback_resolved'));
