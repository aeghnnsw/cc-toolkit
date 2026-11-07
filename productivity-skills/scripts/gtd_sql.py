#!/usr/bin/env python3
"""Render connected Supabase tool arguments. Python 3.11+. No network access."""

import argparse
import base64
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys
import uuid
from zoneinfo import ZoneInfo


TRANSACTION = Path(__file__).resolve().parents[1] / "references" / "gtd-connector-transaction.sql"
KINDS = ("inbox", "action", "project")
DATA_FIELDS = {"kind", "title", "notes", "priority", "duration_label", "due", "start"}
OP_FIELDS = {
    "create": {"op", "id", "data"},
    "patch": {"op", "id", "expected_revision", "patch"},
    **{name: {"op", "id", "expected_revision"} for name in ("complete", "reopen", "delete", "restore")},
    **{name: {"op", "id", "expected_revision", "project_id"} for name in ("link", "unlink")},
}


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("nonfinite JSON number")


def load_json(path):
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"),
                      object_pairs_hook=object_pairs, parse_constant=reject_constant)


def identifier(value):
    if not isinstance(value, str):
        raise ValueError("UUID must be a string")
    return str(uuid.UUID(value))


def validate_date(value):
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError("date must be an object or null")
    kind = value.get("kind")
    if kind == "date_only" and set(value) == {"kind", "date"}:
        day = value["date"]
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError("date must be YYYY-MM-DD")
        date.fromisoformat(day)
        return
    fields = {"kind", "local", "time_zone"} if kind == "zoned_datetime" else {"kind", "local"}
    if kind not in ("floating_datetime", "zoned_datetime") or set(value) != fields:
        raise ValueError("unsupported date shape")
    local = value["local"]
    if not isinstance(local, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?", local):
        raise ValueError("local datetime must include seconds and no offset")
    datetime.fromisoformat(local)
    if kind == "zoned_datetime":
        if not isinstance(value["time_zone"], str):
            raise ValueError("time_zone must name an IANA timezone")
        ZoneInfo(value["time_zone"])


def validate_data(data, create=False):
    if not isinstance(data, dict) or not data or set(data) - DATA_FIELDS:
        raise ValueError("unsupported data fields")
    if create and not {"title", "kind"} <= set(data):
        raise ValueError("create needs title and kind")
    if "kind" in data and data["kind"] not in KINDS:
        raise ValueError("invalid kind")
    if "title" in data and (not isinstance(data["title"], str) or not data["title"].strip()):
        raise ValueError("title must be nonblank text")
    for key in ("notes", "duration_label"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            raise ValueError("invalid text field")
    if "priority" in data and (type(data["priority"]) is not int or not 0 <= data["priority"] <= 9):
        raise ValueError("priority must be an integer from 0 through 9")
    for key in ("due", "start"):
        if key in data:
            validate_date(data[key])


def validate_request(request):
    if not isinstance(request, dict) or set(request) != {"request_id", "operations"}:
        raise ValueError("request requires request_id and operations only")
    request["request_id"] = identifier(request["request_id"])
    operations = request["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= 20:
        raise ValueError("request requires 1 through 20 operations")
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("op"), str):
            raise ValueError("invalid operation")
        name = operation["op"]
        if name not in OP_FIELDS or set(operation) != OP_FIELDS[name]:
            raise ValueError("unsupported operation or fields")
        operation["id"] = identifier(operation["id"])
        if name != "create":
            revision = operation["expected_revision"]
            if type(revision) is not int or not 1 <= revision <= 9223372036854775807:
                raise ValueError("expected_revision must be a positive bigint integer")
        if name in ("link", "unlink"):
            operation["project_id"] = identifier(operation["project_id"])
        if name in ("create", "patch"):
            validate_data(operation["data" if name == "create" else "patch"], create=name == "create")
    return request


def links_query(owner, actions):
    return f"""SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'action_id', l.action_id, 'project_id', l.project_id, 'project_title', p.data->>'title',
        'project_is_completed', p.data->'is_completed', 'project_deleted_at', p.deleted_at
    ) ORDER BY l.action_id, l.project_id), '[]'::jsonb)
    FROM public.gtd_links AS l
    JOIN public.gtd_items AS a ON a.owner_id = l.owner_id AND a.id = l.action_id
    JOIN public.gtd_items AS p ON p.owner_id = l.owner_id AND p.id = l.project_id
    WHERE l.owner_id = '{owner}'::uuid AND l.deleted_at IS NULL
        AND a.data->>'kind' = 'action' AND p.data->>'kind' = 'project'
        AND l.action_id IN ({actions})"""


def render(args):
    config = load_json(args.config)
    if not isinstance(config, dict) or set(config) != {"project_id", "owner_id"}:
        raise ValueError("config requires project_id and owner_id only")
    project = config["project_id"]
    if not isinstance(project, str) or not project or any(c.isspace() or ord(c) < 32 for c in project):
        raise ValueError("invalid project reference")
    owner = identifier(config["owner_id"])
    if args.command == "apply":
        request = validate_request(load_json(args.request))
        request_id = request["request_id"]
        payload = base64.b64encode(json.dumps(request["operations"]).encode()).decode("ascii")
        query = TRANSACTION.read_text().replace("{{OWNER_ID}}", owner)
        query = query.replace("{{REQUEST_ID}}", request_id).replace("{{OPERATIONS_BASE64}}", payload)
        if "{{" in query or "}}" in query:
            raise ValueError("unresolved transaction placeholder")
    elif args.command == "read":
        if not 1 <= args.limit <= 100 or (args.request_count is not None and not 0 <= args.request_count <= 9223372036854775807):
            raise ValueError("invalid page limit or request count")
        after = "NULL::uuid" if args.after is None else f"'{identifier(args.after)}'::uuid"
        kind = "NULL::text" if args.kind is None else f"'{args.kind}'::text"
        baseline = "NULL::bigint" if args.request_count is None else str(args.request_count)
        query = f"""WITH ledger AS (
    SELECT count(*) AS request_count FROM public.gtd_requests WHERE owner_id = '{owner}'::uuid
), candidates AS (
    SELECT i.* FROM public.gtd_items AS i CROSS JOIN ledger AS c
    WHERE i.owner_id = '{owner}'::uuid AND i.deleted_at IS NULL
        AND i.data->'is_completed' IS DISTINCT FROM 'true'::jsonb
        AND ({kind} IS NULL OR i.data->>'kind' = {kind})
        AND ({after} IS NULL OR i.id > {after})
        AND ({baseline} IS NULL OR c.request_count = {baseline})
    ORDER BY i.id LIMIT {args.limit + 1}
), page AS (
    SELECT * FROM candidates ORDER BY id LIMIT {args.limit}
)
SELECT jsonb_build_object(
    'status', CASE WHEN {baseline} IS NOT NULL AND c.request_count <> {baseline}
        THEN 'inventory_changed' ELSE 'ok' END,
    'owner_id', '{owner}'::uuid, 'kind', {kind}, 'scope', 'open',
    'request_count', c.request_count, 'expected_request_count', {baseline},
    'after', {after}, 'limit', {args.limit},
    'rows', (SELECT COALESCE(jsonb_agg(to_jsonb(p) ORDER BY p.id), '[]'::jsonb) FROM page AS p),
    'returned_count', (SELECT count(*) FROM page),
    'has_more', (SELECT count(*) > {args.limit} FROM candidates),
    'next_after', CASE WHEN (SELECT count(*) > {args.limit} FROM candidates)
        THEN (SELECT id FROM page ORDER BY id DESC LIMIT 1) ELSE NULL END,
    'links', ({links_query(owner, 'SELECT id FROM page')})
) AS result FROM ledger AS c;
"""
    elif args.command == "receipt":
        request_id = identifier(args.id)
        query = f"""SELECT COALESCE(r.result, jsonb_build_object(
    'status', 'missing', 'owner_id', '{owner}'::uuid, 'request_id', '{request_id}'::uuid,
    'result_count', 0, 'results', '[]'::jsonb
)) AS result
FROM (SELECT 1) AS anchor
LEFT JOIN public.gtd_requests AS r
ON r.owner_id = '{owner}'::uuid AND r.request_id = '{request_id}'::uuid;
"""
    else:
        item_id = identifier(args.id)
        query = f"""SELECT jsonb_build_object(
    'status', CASE WHEN i.id IS NULL THEN 'missing' ELSE 'ok' END,
    'owner_id', '{owner}'::uuid, 'item', to_jsonb(i),
    'links', ({links_query(owner, 'SELECT i.id')})
) AS result
FROM (SELECT 1) AS anchor
LEFT JOIN public.gtd_items AS i ON i.owner_id = '{owner}'::uuid AND i.id = '{item_id}'::uuid;
"""
    return {"project_id": config["project_id"], "query": query}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="~/.config/cc-toolkit/gtd.json")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("apply").add_argument("request")
    commands.add_parser("get").add_argument("id")
    commands.add_parser("receipt").add_argument("id")
    read = commands.add_parser("read")
    read.add_argument("--kind", choices=KINDS)
    read.add_argument("--after")
    read.add_argument("--limit", type=int, default=50)
    read.add_argument("--request-count", type=int)
    args = parser.parse_args()
    try:
        print(json.dumps(render(args)))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"gtd_sql: invalid input ({type(error).__name__}); no SQL was sent.\n")


if __name__ == "__main__":
    main()
