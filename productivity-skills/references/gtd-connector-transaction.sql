-- Fixed management-connector transaction. The renderer supplies UUIDs and base64 only.
BEGIN;
DO $gtd$
DECLARE
    v_owner uuid := '{{OWNER_ID}}';
    v_request uuid := '{{REQUEST_ID}}';
    v_operations jsonb := convert_from(decode('{{OPERATIONS_BASE64}}', 'base64'), 'UTF8')::jsonb;
    v_operation jsonb;
    v_name text;
    v_fields text[];
    v_data jsonb;
    v_key text;
    v_date jsonb;
    v_stored public.gtd_requests%ROWTYPE;
    v_item public.gtd_items%ROWTYPE;
    v_project public.gtd_items%ROWTYPE;
    v_results jsonb := '[]'::jsonb;
BEGIN
    IF jsonb_typeof(v_operations) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'operations must be an array';
    END IF;
    IF jsonb_array_length(v_operations) NOT BETWEEN 1 AND 20 THEN
        RAISE EXCEPTION 'request requires 1 through 20 operations';
    END IF;
    FOR v_operation IN SELECT value FROM jsonb_array_elements(v_operations)
    LOOP
        IF jsonb_typeof(v_operation) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'operation must be an object';
        END IF;
        v_name := v_operation->>'op';
        CASE v_name
            WHEN 'create' THEN v_fields := ARRAY['op', 'id', 'data'];
            WHEN 'patch' THEN v_fields := ARRAY['op', 'id', 'expected_revision', 'patch'];
            WHEN 'complete', 'reopen', 'delete', 'restore' THEN
                v_fields := ARRAY['op', 'id', 'expected_revision'];
            WHEN 'link', 'unlink' THEN v_fields := ARRAY['op', 'id', 'expected_revision', 'project_id'];
            ELSE RAISE EXCEPTION 'unsupported operation';
        END CASE;
        IF NOT (v_operation ?& v_fields) OR v_operation - v_fields <> '{}'::jsonb THEN
            RAISE EXCEPTION 'unsupported or missing operation fields';
        END IF;
        IF jsonb_typeof(v_operation->'id') IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'id must be a UUID string';
        END IF;
        PERFORM (v_operation->>'id')::uuid;
        IF v_name <> 'create' THEN
            IF jsonb_typeof(v_operation->'expected_revision') IS DISTINCT FROM 'number'
                OR v_operation->>'expected_revision' !~ '^[1-9][0-9]*$'
            THEN
                RAISE EXCEPTION 'expected_revision must be a positive bigint integer';
            END IF;
            PERFORM (v_operation->>'expected_revision')::bigint;
        END IF;
        IF v_name IN ('link', 'unlink') THEN
            IF jsonb_typeof(v_operation->'project_id') IS DISTINCT FROM 'string' THEN
                RAISE EXCEPTION 'project_id must be a UUID string';
            END IF;
            PERFORM (v_operation->>'project_id')::uuid;
        END IF;
        IF v_name IN ('create', 'patch') THEN
            v_data := v_operation->(CASE WHEN v_name = 'create' THEN 'data' ELSE 'patch' END);
            IF jsonb_typeof(v_data) IS DISTINCT FROM 'object' OR v_data = '{}'::jsonb THEN
                RAISE EXCEPTION 'data must be a nonempty object';
            END IF;
            IF v_data - ARRAY['kind', 'title', 'notes', 'priority', 'duration_label', 'due', 'start'] <> '{}'::jsonb THEN
                RAISE EXCEPTION 'unsupported data fields';
            END IF;
            IF v_name = 'create' AND NOT (v_data ?& ARRAY['kind', 'title']) THEN
                RAISE EXCEPTION 'create needs title and kind';
            END IF;
            IF v_data ? 'kind' AND (jsonb_typeof(v_data->'kind') IS DISTINCT FROM 'string'
                OR v_data->>'kind' NOT IN ('inbox', 'action', 'project'))
            THEN
                RAISE EXCEPTION 'invalid kind';
            END IF;
            IF v_data ? 'title' AND (jsonb_typeof(v_data->'title') IS DISTINCT FROM 'string'
                OR v_data->>'title' ~ '^[[:space:]]*$')
            THEN
                RAISE EXCEPTION 'title must be nonblank text';
            END IF;
            FOREACH v_key IN ARRAY ARRAY['notes', 'duration_label'] LOOP
                IF v_data ? v_key AND jsonb_typeof(v_data->v_key) NOT IN ('null', 'string') THEN
                    RAISE EXCEPTION 'invalid text field';
                END IF;
            END LOOP;
            IF v_data ? 'priority' AND (jsonb_typeof(v_data->'priority') IS DISTINCT FROM 'number'
                OR v_data->>'priority' !~ '^[0-9]$')
            THEN
                RAISE EXCEPTION 'priority must be an integer from 0 through 9';
            END IF;
            FOREACH v_key IN ARRAY ARRAY['due', 'start'] LOOP
                v_date := v_data->v_key;
                IF v_date IS NULL OR v_date = 'null'::jsonb THEN
                    CONTINUE;
                END IF;
                IF jsonb_typeof(v_date) IS DISTINCT FROM 'object' THEN
                    RAISE EXCEPTION 'date must be an object or null';
                END IF;
                CASE v_date->>'kind'
                    WHEN 'date_only' THEN v_fields := ARRAY['kind', 'date'];
                    WHEN 'floating_datetime' THEN v_fields := ARRAY['kind', 'local'];
                    WHEN 'zoned_datetime' THEN v_fields := ARRAY['kind', 'local', 'time_zone'];
                    ELSE RAISE EXCEPTION 'unsupported date shape';
                END CASE;
                IF NOT (v_date ?& v_fields) OR v_date - v_fields <> '{}'::jsonb THEN
                    RAISE EXCEPTION 'unsupported date fields';
                END IF;
                IF v_date->>'kind' = 'date_only' THEN
                    IF jsonb_typeof(v_date->'date') IS DISTINCT FROM 'string'
                        OR v_date->>'date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                    THEN
                        RAISE EXCEPTION 'date must be YYYY-MM-DD';
                    END IF;
                    PERFORM (v_date->>'date')::date;
                ELSE
                    IF jsonb_typeof(v_date->'local') IS DISTINCT FROM 'string'
                        OR v_date->>'local' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?$'
                    THEN
                        RAISE EXCEPTION 'local datetime must include seconds and no offset';
                    END IF;
                    PERFORM (v_date->>'local')::timestamp;
                    IF v_date->>'kind' = 'zoned_datetime' AND (
                        jsonb_typeof(v_date->'time_zone') IS DISTINCT FROM 'string'
                        OR NOT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = v_date->>'time_zone'))
                    THEN
                        RAISE EXCEPTION 'time_zone must name an IANA timezone';
                    END IF;
                END IF;
            END LOOP;
        END IF;
    END LOOP;
    INSERT INTO public.gtd_requests (owner_id, request_id, operations)
    VALUES (v_owner, v_request, v_operations) ON CONFLICT DO NOTHING;
    SELECT * INTO STRICT v_stored FROM public.gtd_requests
    WHERE owner_id = v_owner AND request_id = v_request FOR UPDATE;
    IF v_stored.operations IS DISTINCT FROM v_operations THEN
        RAISE EXCEPTION 'request payload mismatch';
    END IF;
    IF v_stored.result IS NOT NULL THEN
        RETURN;
    END IF;
    FOR v_operation IN SELECT value FROM jsonb_array_elements(v_operations)
    LOOP
        IF v_operation->>'op' = 'create' THEN
            INSERT INTO public.gtd_items (id, owner_id, data)
            VALUES (
                (v_operation->>'id')::uuid, v_owner,
                '{"is_completed":false,"completion_date":null,"due":null,"notes":null,"priority":5,"duration_label":null}'::jsonb
                    || (v_operation->'data')
            ) RETURNING * INTO v_item;
        ELSE
            SELECT * INTO v_item FROM public.gtd_items
            WHERE owner_id = v_owner AND id = (v_operation->>'id')::uuid FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'owned item missing';
            END IF;
            IF v_item.revision <> (v_operation->>'expected_revision')::bigint THEN
                RAISE EXCEPTION 'revision conflict';
            END IF;
            IF v_item.deleted_at IS NOT NULL AND v_operation->>'op' <> 'restore' THEN
                RAISE EXCEPTION 'deleted item must be restored first';
            END IF;
            CASE v_operation->>'op'
                WHEN 'patch' THEN
                    IF v_operation->'patch' ? 'kind' AND v_item.data->>'kind' <> 'inbox'
                        AND v_operation->'patch'->>'kind' IS DISTINCT FROM v_item.data->>'kind'
                    THEN
                        RAISE EXCEPTION 'only inbox kind can change';
                    END IF;
                    v_item.data := v_item.data || (v_operation->'patch');
                WHEN 'complete' THEN
                    v_item.data := v_item.data || jsonb_build_object(
                        'is_completed', true, 'completion_date', clock_timestamp());
                WHEN 'reopen' THEN
                    v_item.data := v_item.data || '{"is_completed":false,"completion_date":null}'::jsonb;
                WHEN 'delete' THEN
                    v_item.deleted_at := clock_timestamp();
                WHEN 'restore' THEN
                    v_item.deleted_at := NULL;
                WHEN 'link', 'unlink' THEN
                    IF v_item.data->>'kind' <> 'action'
                        OR v_item.id = (v_operation->>'project_id')::uuid
                    THEN
                        RAISE EXCEPTION 'link requires distinct action and project';
                    END IF;
                    SELECT * INTO v_project FROM public.gtd_items
                    WHERE owner_id = v_owner AND id = (v_operation->>'project_id')::uuid FOR SHARE;
                    IF NOT FOUND OR v_project.deleted_at IS NOT NULL OR v_project.data->>'kind' <> 'project' THEN
                        RAISE EXCEPTION 'owned live project missing';
                    END IF;
                    INSERT INTO public.gtd_links (owner_id, action_id, project_id, deleted_at)
                    VALUES (v_owner, v_item.id, v_project.id,
                        CASE WHEN v_operation->>'op' = 'unlink' THEN clock_timestamp() ELSE NULL END)
                    ON CONFLICT (owner_id, action_id, project_id)
                    DO UPDATE SET deleted_at = EXCLUDED.deleted_at;
                ELSE
                    RAISE EXCEPTION 'unsupported operation';
            END CASE;
            UPDATE public.gtd_items SET
                data = v_item.data, deleted_at = v_item.deleted_at,
                revision = revision + 1, updated_at = clock_timestamp()
            WHERE owner_id = v_owner AND id = v_item.id RETURNING * INTO v_item;
        END IF;
        v_results := v_results || jsonb_build_array(jsonb_build_object(
            'op', v_operation->>'op', 'id', v_item.id, 'revision', v_item.revision
        ) || CASE WHEN v_operation->>'op' IN ('link', 'unlink')
            THEN jsonb_build_object('project_id', (v_operation->>'project_id')::uuid)
            ELSE '{}'::jsonb END);
    END LOOP;
    UPDATE public.gtd_requests SET result = jsonb_build_object(
        'status', 'committed', 'owner_id', v_owner, 'request_id', v_request,
        'result_count', jsonb_array_length(v_results), 'results', v_results
    ) WHERE owner_id = v_owner AND request_id = v_request;
END;
$gtd$;
COMMIT;
SELECT result FROM public.gtd_requests
WHERE owner_id = '{{OWNER_ID}}'::uuid AND request_id = '{{REQUEST_ID}}'::uuid;
