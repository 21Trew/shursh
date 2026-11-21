-- Explicit finished state preserves participant links, assignments and history.
ALTER TABLE public.santa_events DROP CONSTRAINT IF EXISTS santa_events_status_check;
ALTER TABLE public.santa_events ADD CONSTRAINT santa_events_status_check
 CHECK (status IN ('open','drawn','finished'));
