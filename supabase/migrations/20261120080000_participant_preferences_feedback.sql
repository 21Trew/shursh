-- Additive Santa preference/profile migration and server-only developer inbox.
-- Existing gift-level columns remain intact for historical data.
ALTER TABLE public.participants
 ADD COLUMN wanted text NOT NULL DEFAULT '' CHECK (char_length(wanted)<=2000),
 ADD COLUMN unwanted text NOT NULL DEFAULT '' CHECK (char_length(unwanted)<=2000);

-- Preserve legacy notes: combine in card ID order only for participants
-- without existing profile preferences (new columns are initially empty).
WITH originals AS (
 SELECT participant_id,
   left(string_agg(nullif(btrim(wanted),''), E'\n' ORDER BY id),2000) AS wanted,
   left(string_agg(nullif(btrim(unwanted),''), E'\n' ORDER BY id),2000) AS unwanted
 FROM public.participant_wishes GROUP BY participant_id
)
UPDATE public.participants p
SET wanted=coalesce(o.wanted,''),unwanted=coalesce(o.unwanted,'')
FROM originals o WHERE p.id=o.participant_id;

CREATE TABLE public.developer_feedback (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
 email text NOT NULL CHECK (char_length(email)<=200),
 topic text NOT NULL CHECK (topic IN ('idea','bug','question','other')),
 message text NOT NULL CHECK (char_length(btrim(message)) BETWEEN 5 AND 3000),
 status text NOT NULL DEFAULT 'new' CHECK(status IN ('new','resolved')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX developer_feedback_created_idx ON public.developer_feedback(id DESC);
ALTER TABLE public.developer_feedback ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.developer_feedback FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.developer_feedback TO shursh_backend;
GRANT USAGE,SELECT ON SEQUENCE public.developer_feedback_id_seq TO shursh_backend;
CREATE POLICY developer_feedback_backend_only ON public.developer_feedback
 FOR ALL TO shursh_backend USING (true) WITH CHECK (true);
