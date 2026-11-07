CREATE TABLE public.gtd_items (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL,
    data jsonb NOT NULL,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    source_namespace text,
    source_id text,
    source_record jsonb,
    UNIQUE (owner_id, id),
    UNIQUE (owner_id, source_namespace, source_id),
    CHECK (jsonb_typeof(data) = 'object'),
    CHECK (jsonb_typeof(data->'title') = 'string' AND btrim(data->>'title') <> ''),
    CHECK (data->>'kind' IN ('inbox', 'action', 'project'))
);
CREATE TABLE public.gtd_links (
    owner_id uuid NOT NULL,
    action_id uuid NOT NULL,
    project_id uuid NOT NULL,
    deleted_at timestamptz,
    PRIMARY KEY (owner_id, action_id, project_id),
    FOREIGN KEY (owner_id, action_id) REFERENCES public.gtd_items (owner_id, id),
    FOREIGN KEY (owner_id, project_id) REFERENCES public.gtd_items (owner_id, id),
    CHECK (action_id <> project_id)
);
CREATE TABLE public.gtd_requests (
    owner_id uuid NOT NULL,
    request_id uuid NOT NULL,
    operations jsonb NOT NULL,
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, request_id)
);
CREATE TABLE public.gtd_snapshots (id integer PRIMARY KEY, payload bytea NOT NULL);
INSERT INTO public.gtd_snapshots VALUES (1, decode('000102ff414243', 'hex'));
CREATE FUNCTION public.gtd_immutable_source() RETURNS trigger LANGUAGE plpgsql AS $$
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
CREATE TRIGGER immutable_source BEFORE UPDATE ON public.gtd_items
FOR EACH ROW EXECUTE FUNCTION public.gtd_immutable_source();
