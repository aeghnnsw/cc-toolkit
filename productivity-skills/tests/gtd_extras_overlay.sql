-- Test overlay: the optional migration records, applied after the shipped references/gtd-schema.sql.
ALTER TABLE public.gtd_items
    ADD COLUMN source_namespace text,
    ADD COLUMN source_id text,
    ADD COLUMN source_record jsonb,
    ADD UNIQUE (owner_id, source_namespace, source_id),
    ADD CHECK ((source_namespace IS NULL) = (source_id IS NULL));
CREATE TABLE public.gtd_snapshots (
    owner_id uuid NOT NULL,
    sha256 text NOT NULL,
    snapshot_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, sha256),
    CHECK (sha256 = encode(sha256(convert_to(snapshot_text, 'UTF8')), 'hex'))
);
INSERT INTO public.gtd_snapshots (owner_id, sha256, snapshot_text)
SELECT '00000000-0000-4000-8000-000000000001', encode(sha256(convert_to(t, 'UTF8')), 'hex'), t
FROM (VALUES (E'synthetic snapshot\n雪 ☃')) AS snapshot (t);
CREATE FUNCTION public.gtd_preserve_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id, NEW.owner_id, NEW.source_namespace, NEW.source_id, NEW.source_record)
        IS DISTINCT FROM
        (OLD.id, OLD.owner_id, OLD.source_namespace, OLD.source_id, OLD.source_record)
    THEN
        RAISE EXCEPTION 'immutable source';
    END IF;
    IF OLD.data->>'kind' <> 'inbox'
        AND NEW.data->>'kind' IS DISTINCT FROM OLD.data->>'kind'
    THEN
        RAISE EXCEPTION 'immutable kind';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER gtd_preserve_source BEFORE UPDATE ON public.gtd_items
FOR EACH ROW EXECUTE FUNCTION public.gtd_preserve_source();
