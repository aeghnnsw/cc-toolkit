-- GTD schema for the Productivity Skills GTD workflows: items, links, and requests.
-- The gtd-setup skill applies this file unchanged. It is safe to apply more than one time.
-- It is plain PostgreSQL. Row-level security is enabled with no policy, and no public role gets a grant.
CREATE TABLE IF NOT EXISTS public.gtd_items (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL,
    data jsonb NOT NULL,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    CONSTRAINT gtd_items_data_check CHECK (COALESCE(
        jsonb_typeof(data) = 'object'
        AND jsonb_typeof(data->'title') = 'string'
        AND btrim(data->>'title') <> ''
        AND data->>'kind' IN ('inbox', 'action', 'project'),
        false))
);
CREATE TABLE IF NOT EXISTS public.gtd_links (
    owner_id uuid NOT NULL,
    action_id uuid NOT NULL,
    project_id uuid NOT NULL,
    deleted_at timestamptz,
    PRIMARY KEY (owner_id, action_id, project_id),
    FOREIGN KEY (owner_id, action_id) REFERENCES public.gtd_items (owner_id, id),
    FOREIGN KEY (owner_id, project_id) REFERENCES public.gtd_items (owner_id, id),
    CHECK (action_id <> project_id)
);
CREATE TABLE IF NOT EXISTS public.gtd_requests (
    owner_id uuid NOT NULL,
    request_id uuid NOT NULL,
    operations jsonb NOT NULL,
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, request_id)
);
CREATE INDEX IF NOT EXISTS gtd_links_project ON public.gtd_links (owner_id, project_id);
ALTER TABLE public.gtd_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gtd_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gtd_requests ENABLE ROW LEVEL SECURITY;
-- Supabase can grant table privileges to its public API roles. Plain PostgreSQL does not have these roles.
DO $gtd_schema$
DECLARE
    v_role text;
BEGIN
    FOREACH v_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
            EXECUTE format(
                'REVOKE ALL ON TABLE public.gtd_items, public.gtd_links, public.gtd_requests FROM %I', v_role);
        END IF;
    END LOOP;
END
$gtd_schema$;
