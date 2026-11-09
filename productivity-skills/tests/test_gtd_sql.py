"""Public renderer and synthetic PostgreSQL contract tests. No hosted services."""

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN / "scripts" / "gtd_sql.py"
SCHEMA = PLUGIN / "references" / "gtd-schema.sql"
OWNER = "00000000-0000-4000-8000-000000000001"
OTHER_OWNER = "00000000-0000-4000-8000-000000000002"


class RendererCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="gtd-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"project_id": "synthetic-project", "owner_id": OWNER}))

    def cli(self, *args, ok=True, config=None, script=SCRIPT):
        process = subprocess.run(
            [sys.executable, str(script), "--config", str(config or self.config), *args],
            text=True, capture_output=True, timeout=10,
        )
        if ok:
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(set(result), {"project_id", "query"})
            self.assertEqual(result["project_id"], "synthetic-project")
            return result["query"]
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(process.stdout, "")
        self.assertNotIn("Traceback", process.stderr)
        return process.stderr

    def request(self, operations, request_id=None):
        path = self.root / f"{uuid.uuid4()}.json"
        path.write_text(json.dumps({"request_id": request_id or str(uuid.uuid4()), "operations": operations}))
        return path


class RendererTests(RendererCase):
    def test_invalid_private_route_never_emits_sql(self):
        for content in (
            '{}', '[]', 'null', '{',
            '{"owner_id":"not-a-uuid","project_id":"synthetic-project"}',
            json.dumps({"owner_id": OWNER, "project_id": ""}),
            json.dumps({"owner_id": OWNER, "project_id": "bad project"}),
            json.dumps({"owner_id": OWNER, "project_id": 3}),
            json.dumps({"owner_id": OWNER, "project_id": "synthetic-project", "token": "PRIVATE"}),
            '{"owner_id":"' + OWNER + '","project_id":"one","project_id":"two"}',
            '{"owner_id":"' + OWNER + '","project_id":NaN}',
        ):
            with self.subTest(content=content):
                self.config.write_text(content)
                error = self.cli("get", str(uuid.uuid4()), ok=False)
                self.assertNotIn("PRIVATE", error)
        self.config.unlink()
        self.cli("get", str(uuid.uuid4()), ok=False)

    def test_invalid_requests_never_emit_sql(self):
        item_id = str(uuid.uuid4())
        create = {"op": "create", "id": item_id, "data": {"kind": "inbox", "title": "Capture"}}
        bad_operations = [
            None, {}, [], [create] * 21, [None],
            [{**create, "op": "import"}], [{**create, "id": "not-a-uuid"}],
            [{**create, "owner_id": OTHER_OWNER}],
            [{"op": "patch", "id": item_id, "expected_revision": 1, "patch": {}}],
        ]
        for revision in (None, 0, -1, True, 1.0, "1", 9223372036854775808):
            bad_operations.append([{"op": "complete", "id": item_id, "expected_revision": revision}])
        for data in (None, [], {}, {"kind": "action"}, {"title": "Capture"},
                     {"kind": "other", "title": "Capture"},
                     {"kind": "inbox", "title": " \n\t"},
                     {"kind": "inbox", "title": 7}):
            bad_operations.append([{**create, "data": data}])
        for key, value in (("source_record", {}), ("is_completed", True), ("completion_date", None),
                           ("notes", 3), ("duration_label", []), ("priority", True),
                           ("priority", -1), ("priority", 10), ("priority", 3.0)):
            bad_operations.append([{**create, "data": {**create["data"], key: value}}])
        for operations in bad_operations:
            with self.subTest(operations=operations):
                self.cli("apply", str(self.request(operations)), ok=False)
        for content in ('[]', '{}', 'null', '{',
                        '{"request_id":"' + str(uuid.uuid4()) + '","operations":[],"extra":1}',
                        '{"request_id":"' + str(uuid.uuid4()) + '","operations":[],"operations":[]}',
                        '{"request_id":"' + str(uuid.uuid4()) + '","operations":[NaN]}'):
            path = self.root / "bad.json"
            path.write_text(content)
            self.cli("apply", str(path), ok=False)
        self.cli("get", "invalid", ok=False)

    def test_deadlines_require_explicit_date_semantics(self):
        for value in (
            None,
            {"kind": "date_only", "date": "2026-12-31"},
            {"kind": "floating_datetime", "local": "2026-12-31T09:00:00"},
            {"kind": "zoned_datetime", "local": "2026-12-31T09:00:00", "time_zone": "America/New_York"},
        ):
            with self.subTest(value=value):
                path = self.request([{"op": "create", "id": str(uuid.uuid4()),
                                      "data": {"kind": "action", "title": "Deadline", "due": value, "start": value}}])
                self.assertEqual(self.cli("apply", str(path)), self.cli("apply", str(path)))
        for value in ("2026-12-31", {}, {"kind": "date_only", "date": "2026-02-30"},
                      {"kind": "date_only", "date": "20261231"},
                      {"kind": "date_only", "date": "2026-12-31", "time_zone": "UTC"},
                      {"kind": "floating_datetime", "local": "2026-12-31T09:00:00Z"},
                      {"kind": "floating_datetime", "local": "2026-12-31"},
                      {"kind": "zoned_datetime", "local": "2026-12-31T09:00:00", "time_zone": "Imaginary/Place"},
                      {"kind": "zoned_datetime", "local": "2026-12-31T09:00:00"}):
            with self.subTest(value=value):
                self.cli("apply", str(self.request([{"op": "patch", "id": str(uuid.uuid4()),
                    "expected_revision": 1, "patch": {"due": value}}])), ok=False)

    def test_incomplete_packaged_template_never_emits_sql(self):
        script_dir = self.root / "package" / "scripts"
        resource_dir = self.root / "package" / "references"
        script_dir.mkdir(parents=True)
        resource_dir.mkdir()
        script = script_dir / "gtd_sql.py"
        shutil.copyfile(SCRIPT, script)
        template = resource_dir / "gtd-connector-transaction.sql"
        template.write_text("SELECT '{{UNRESOLVED}}';")
        path = self.request([{"op": "create", "id": str(uuid.uuid4()),
                             "data": {"kind": "inbox", "title": "Capture"}}])
        self.cli("apply", str(path), script=script, ok=False)
        template.unlink()
        self.cli("apply", str(path), script=script, ok=False)


class DatabaseCase(RendererCase):
    """One disposable PostgreSQL server for the module; one database for each test class."""
    overlay = None
    server = None

    @classmethod
    def start_server(cls):
        if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "psql")):
            raise unittest.SkipTest("PostgreSQL tools are required for SQL contract tests")
        cluster = tempfile.TemporaryDirectory(prefix="pg-")
        unittest.addModuleCleanup(cluster.cleanup)
        root = Path(cluster.name)
        data, socket = root / "db", root / "s"
        socket.mkdir(mode=0o700)
        subprocess.run(
            ["initdb", "-D", str(data), "-A", "trust", "-U", "gtd_test", "--no-locale", "--encoding=UTF8"],
            check=True, capture_output=True, text=True, timeout=30,
        )
        unittest.addModuleCleanup(cls.stop_server, data)
        subprocess.run(
            ["pg_ctl", "-D", str(data), "-l", str(root / "postgres.log"),
             "-o", f"-h '' -k {socket}", "-w", "start"],
            check=True, capture_output=True, text=True, timeout=30,
        )
        DatabaseCase.server = ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-h", str(socket),
                               "-U", "gtd_test", "-A", "-t", "-q", "-d"]

    @staticmethod
    def stop_server(data):
        if (data / "postmaster.pid").exists():
            subprocess.run(["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"],
                           check=True, capture_output=True, text=True, timeout=30)

    @classmethod
    def create_database(cls, *scripts):
        """Create an empty database, run the SQL scripts in it, and return its psql command."""
        name = f"gtd_{uuid.uuid4().hex}"
        subprocess.run([*cls.server, "postgres"], input=f"CREATE DATABASE {name};",
                       text=True, capture_output=True, check=True, timeout=30)
        command = [*cls.server, name]
        for script in scripts:
            subprocess.run(command, input=script.read_text(), text=True, capture_output=True, check=True, timeout=10)
        return command

    @classmethod
    def setUpClass(cls):
        if DatabaseCase.server is None:
            cls.start_server()
        cls.psql_command = cls.create_database(SCHEMA, *([cls.overlay] if cls.overlay else []))

    def setUp(self):
        super().setUp()
        self.sql("TRUNCATE public.gtd_links, public.gtd_items, public.gtd_requests;")

    def sql(self, query, ok=True):
        process = subprocess.run(self.psql_command, input=query, text=True, capture_output=True, timeout=15)
        if ok:
            self.assertEqual(process.returncode, 0, process.stderr)
            lines = process.stdout.strip().splitlines()
            return json.loads(lines[-1]) if lines else None
        self.assertNotEqual(process.returncode, 0)
        return process.stderr

    def apply(self, operations, request_id=None, ok=True, config=None):
        return self.sql(self.cli("apply", str(self.request(operations, request_id)), config=config), ok=ok)

    def get(self, item_id):
        return self.sql(self.cli("get", item_id))


class ShippedSchemaTests(DatabaseCase):
    """The shipped schema alone, without the optional migration records."""

    def test_schema_applies_twice_and_revokes_public_api_roles(self):
        command = self.create_database(SCHEMA)
        tables = "public.gtd_items, public.gtd_links, public.gtd_requests"
        setup = f"""DO $roles$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon; END IF;
            END $roles$;
            GRANT ALL ON TABLE {tables} TO anon;
            INSERT INTO public.gtd_items (id, owner_id, data)
            VALUES ('{uuid.uuid4()}', '{OWNER}', '{{"kind":"inbox","title":"Kept"}}');"""
        subprocess.run(command, input=setup, text=True, capture_output=True, check=True, timeout=10)
        again = subprocess.run(command, input=SCHEMA.read_text(), text=True, capture_output=True, timeout=10)
        self.assertEqual(again.returncode, 0, again.stderr)
        state = subprocess.run(command, input="""SELECT jsonb_build_object(
            'items', (SELECT count(*) FROM public.gtd_items),
            'anon', (SELECT count(*) FROM information_schema.role_table_grants
                     WHERE table_schema = 'public' AND grantee = 'anon'));""",
                               text=True, capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(state.stdout), {"items": 1, "anon": 0})

    def test_tables_have_row_level_security_no_policy_and_no_public_grant(self):
        state = self.sql("""SELECT jsonb_build_object(
            'secured', (SELECT jsonb_object_agg(relname, relrowsecurity) FROM pg_class
                        WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'),
            'policies', (SELECT count(*) FROM pg_policies WHERE schemaname = 'public'),
            'public_grants', (SELECT count(*) FROM information_schema.role_table_grants
                              WHERE table_schema = 'public' AND grantee = 'PUBLIC'));""")
        self.assertEqual(state, {"secured": {"gtd_items": True, "gtd_links": True, "gtd_requests": True},
                                 "policies": 0, "public_grants": 0})

    def test_create_read_link_complete_delete_restore(self):
        action_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
        receipt = self.apply([
            {"op": "create", "id": action_id, "data": {"kind": "action", "title": "Step"}},
            {"op": "create", "id": project_id, "data": {"kind": "project", "title": "Outcome"}},
        ])
        self.assertEqual(receipt["status"], "committed")
        page = self.sql(self.cli("read"))
        self.assertEqual(page["status"], "ok")
        self.assertEqual({row["id"] for row in page["rows"]}, {action_id, project_id})
        self.assertEqual(set(page["rows"][0]),
                         {"id", "owner_id", "data", "revision", "deleted_at", "created_at", "updated_at"})
        self.apply([{"op": "link", "id": action_id, "expected_revision": 1, "project_id": project_id}])
        self.assertEqual(self.get(action_id)["links"][0]["project_id"], project_id)
        self.apply([{"op": "complete", "id": action_id, "expected_revision": 2}])
        self.assertTrue(self.get(action_id)["item"]["data"]["is_completed"])
        self.assertEqual([row["id"] for row in self.sql(self.cli("read"))["rows"]], [project_id])
        self.apply([{"op": "delete", "id": action_id, "expected_revision": 3}])
        self.assertIsNotNone(self.get(action_id)["item"]["deleted_at"])
        self.apply([{"op": "restore", "id": action_id, "expected_revision": 4}])
        item = self.get(action_id)["item"]
        self.assertIsNone(item["deleted_at"])
        self.assertEqual(item["revision"], 5)
        self.assertEqual(self.get(action_id)["links"][0]["project_title"], "Outcome")

    def test_item_check_rejects_missing_title_and_missing_kind(self):
        insert = "INSERT INTO public.gtd_items (id, owner_id, data) VALUES ('{}', '{}', '{}');"
        for data in ({"kind": "inbox"}, {"title": "No kind"}, {"kind": "inbox", "title": " "},
                     {"kind": "other", "title": "Unknown kind"}, []):
            with self.subTest(data=data):
                error = self.sql(insert.format(uuid.uuid4(), OWNER, json.dumps(data)), ok=False)
                self.assertIn("gtd_items_data_check", error)
        self.sql(insert.format(uuid.uuid4(), OWNER, json.dumps({"kind": "inbox", "title": "Valid"})))
        self.assertEqual(self.sql(self.cli("read"))["returned_count"], 1)


class DatabaseTests(DatabaseCase):
    """The contract on the shipped schema with the optional migration records."""
    overlay = Path(__file__).parent / "gtd_extras_overlay.sql"

    def snapshot(self):
        return self.sql("""SELECT jsonb_agg(jsonb_build_array(owner_id, snapshot_text,
            sha256 = encode(sha256(convert_to(snapshot_text, 'UTF8')), 'hex'))) FROM public.gtd_snapshots;""")

    def test_create_keeps_hostile_text_and_server_defaults(self):
        item_id = str(uuid.uuid4())
        title = "O'Brien'); DROP TABLE public.gtd_items; --\n雪 ☃"
        receipt = self.apply([{"op": "create", "id": item_id, "data": {"kind": "inbox", "title": title}}])
        self.assertEqual(receipt["status"], "committed")
        self.assertEqual(receipt["owner_id"], OWNER)
        self.assertEqual(receipt["result_count"], 1)
        self.assertEqual(receipt["results"], [{"op": "create", "id": item_id, "revision": 1}])
        item = self.get(item_id)["item"]
        self.assertEqual(item["data"], {"kind": "inbox", "title": title, "is_completed": False,
                                      "completion_date": None, "due": None, "notes": None,
                                      "priority": 5, "duration_label": None})
        self.assertEqual(item["revision"], 1)
        self.assertIsNone(item["source_record"])

    def test_exact_replay_returns_original_receipt_after_later_edits(self):
        item_id, request_id = str(uuid.uuid4()), str(uuid.uuid4())
        operations = [{"op": "create", "id": item_id, "data": {"kind": "action", "title": "Original"}}]
        receipt = self.apply(operations, request_id)
        self.assertEqual(self.apply(operations, request_id), receipt)
        self.assertEqual(self.apply([{"data": {"title": "Original", "kind": "action"},
                                     "id": item_id, "op": "create"}], request_id), receipt)
        edited = self.apply([{"op": "patch", "id": item_id, "expected_revision": 1,
                              "patch": {"title": "Later title", "priority": 0}}])
        self.assertEqual(edited["results"][0]["revision"], 2)
        self.assertEqual(self.apply(operations, request_id), receipt)
        self.assertEqual(self.sql(self.cli("receipt", request_id)), receipt)
        operations[0]["data"]["title"] = "Changed payload"
        self.assertIn("request payload mismatch", self.apply(operations, request_id, ok=False))
        item = self.get(item_id)["item"]
        self.assertEqual(item["data"]["title"], "Later title")
        self.assertEqual(item["data"]["priority"], 0)
        self.assertEqual(item["revision"], 2)

    def test_lifecycle_preserves_imported_fields_source_and_snapshot(self):
        item_id = str(uuid.uuid4())
        self.sql(f"""INSERT INTO public.gtd_items
            (id, owner_id, data, source_namespace, source_id, source_record) VALUES
            ('{item_id}', '{OWNER}',
             '{{"kind":"action","title":"Imported","notes":"Keep me","priority":0,
                "duration_label":null,"is_completed":false,"completion_date":null,
                "due":{{"raw_components":{{"year":2026}}}},"unknown_import":{{"a":1}}}}',
             'synthetic', 'old-1', '{{"bytes":"original","null_date":null}}');""")
        original = self.get(item_id)["item"]
        self.apply([{"op": "complete", "id": item_id, "expected_revision": 1}])
        complete = self.get(item_id)["item"]
        self.assertTrue(complete["data"]["is_completed"])
        self.assertIsNotNone(complete["data"]["completion_date"])
        self.apply([{"op": "reopen", "id": item_id, "expected_revision": 2},
                    {"op": "delete", "id": item_id, "expected_revision": 3}])
        deleted = self.get(item_id)["item"]
        self.assertFalse(deleted["data"]["is_completed"])
        self.assertIsNone(deleted["data"]["completion_date"])
        self.assertIsNotNone(deleted["deleted_at"])
        self.assertIn("deleted item", self.apply([
            {"op": "patch", "id": item_id, "expected_revision": 4, "patch": {"notes": "Blocked"}}
        ], ok=False))
        self.apply([{"op": "restore", "id": item_id, "expected_revision": 4},
                    {"op": "patch", "id": item_id, "expected_revision": 5, "patch": {"title": "Renamed"}}])
        current = self.get(item_id)["item"]
        self.assertEqual(current["revision"], 6)
        self.assertIsNone(current["deleted_at"])
        self.assertEqual(current["data"], {**original["data"], "title": "Renamed"})
        for key in ("source_namespace", "source_id", "source_record", "created_at"):
            self.assertEqual(current[key], original[key])
        self.assertEqual(self.snapshot(), [[OWNER, "synthetic snapshot\n雪 ☃", True]])

    def test_source_identity_is_paired_and_immutable(self):
        item_id = str(uuid.uuid4())
        insert = """INSERT INTO public.gtd_items (id, owner_id, data, source_namespace, source_id)
            VALUES ('{}', '{}', '{{"kind":"inbox","title":"Imported"}}', 'synthetic', {});"""
        self.assertIn("violates check constraint", self.sql(insert.format(uuid.uuid4(), OWNER, "NULL"), ok=False))
        self.sql(insert.format(item_id, OWNER, "'old-1'"))
        self.assertIn("duplicate key", self.sql(insert.format(uuid.uuid4(), OWNER, "'old-1'"), ok=False))
        self.assertIn("immutable source", self.sql(
            f"UPDATE public.gtd_items SET source_id = 'old-2' WHERE id = '{item_id}';", ok=False))
        self.assertEqual(self.get(item_id)["item"]["source_id"], "old-1")

    def test_inventory_pages_are_complete_owned_and_invalidated_by_new_requests(self):
        ids = [f"10000000-0000-4000-8000-{number:012d}" for number in range(1, 8)]
        self.apply([{"op": "create", "id": item_id,
                     "data": {"kind": "action" if index % 2 else "inbox", "title": "Repeated title"}}
                    for index, item_id in enumerate(ids)])
        self.apply([{"op": "complete", "id": ids[-1], "expected_revision": 1},
                    {"op": "delete", "id": ids[-2], "expected_revision": 1}])
        self.sql(f"""INSERT INTO public.gtd_items (id,owner_id,data)
            VALUES ('20000000-0000-4000-8000-000000000001','{OTHER_OWNER}',
                    '{{"kind":"action","title":"Other owner"}}');
            INSERT INTO public.gtd_requests (owner_id,request_id,operations)
            VALUES ('{OTHER_OWNER}','20000000-0000-4000-8000-000000000002','[]');""")
        first = self.sql(self.cli("read", "--limit", "2"))
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["owner_id"], OWNER)
        self.assertEqual(first["request_count"], 2)
        self.assertEqual(first["returned_count"], 2)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["next_after"], ids[1])
        seen = [row["id"] for row in first["rows"]]
        page = first
        while page["has_more"]:
            page = self.sql(self.cli("read", "--limit", "2", "--after", page["next_after"],
                                    "--request-count", "2"))
            self.assertEqual(page["status"], "ok")
            self.assertEqual(page["returned_count"], len(page["rows"]))
            seen.extend(row["id"] for row in page["rows"])
        self.assertEqual(seen, ids[:5])
        self.assertIsNone(page["next_after"])
        self.assertEqual(self.sql(self.cli("read", "--limit", "1", "--request-count", "2"))["status"], "ok")
        actions = self.sql(self.cli("read", "--kind", "action"))
        self.assertEqual([row["id"] for row in actions["rows"]], [ids[1], ids[3]])
        self.assertEqual(self.get("20000000-0000-4000-8000-000000000001")["status"], "missing")
        self.assertEqual(self.get(ids[-1])["status"], "ok")
        self.assertEqual(self.get(ids[-2])["status"], "ok")
        self.apply([{"op": "patch", "id": ids[0], "expected_revision": 1, "patch": {"title": "Changed"}}])
        changed = self.sql(self.cli("read", "--after", ids[1], "--request-count", "2"))
        self.assertEqual(changed["status"], "inventory_changed")
        self.assertEqual(changed["request_count"], 3)
        self.assertEqual(changed["rows"], [])

    def test_links_survive_project_completion_and_deletion_without_changing_actions(self):
        action_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.sql(f"""INSERT INTO public.gtd_items
            (id,owner_id,data,source_namespace,source_id,source_record)
            VALUES ('{action_id}','{OWNER}','{{"kind":"inbox","title":"Step","is_completed":false}}',
                    'synthetic','link-source','{{"original":"capture"}}');""")
        imported = self.get(action_id)["item"]
        receipt = self.apply([
            {"op": "create", "id": project_id, "data": {"kind": "project", "title": "Outcome"}},
            {"op": "patch", "id": action_id, "expected_revision": 1, "patch": {"kind": "action"}},
            {"op": "link", "id": action_id, "expected_revision": 2, "project_id": project_id},
        ])
        self.assertEqual(receipt["results"][-1], {"op": "link", "id": action_id, "revision": 3,
                                                   "project_id": project_id})
        original_action = self.get(action_id)["item"]
        links = self.get(action_id)["links"]
        self.assertEqual(links, [{"action_id": action_id, "project_id": project_id,
                                  "project_title": "Outcome", "project_is_completed": False,
                                  "project_deleted_at": None}])
        self.apply([{"op": "complete", "id": project_id, "expected_revision": 1},
                    {"op": "delete", "id": project_id, "expected_revision": 2}])
        self.assertEqual(self.get(action_id)["item"], original_action)
        page = self.sql(self.cli("read", "--kind", "action"))
        self.assertEqual(page["links"][0]["project_id"], project_id)
        self.assertTrue(page["links"][0]["project_is_completed"])
        self.assertIsNotNone(page["links"][0]["project_deleted_at"])
        self.apply([{"op": "restore", "id": project_id, "expected_revision": 3},
                    {"op": "reopen", "id": project_id, "expected_revision": 4},
                    {"op": "unlink", "id": action_id, "expected_revision": 3, "project_id": project_id}])
        self.assertEqual(self.get(action_id)["links"], [])
        self.apply([{"op": "link", "id": action_id, "expected_revision": 4, "project_id": project_id}])
        self.assertEqual(self.get(action_id)["links"], links)
        current = self.get(action_id)["item"]
        for key in ("source_namespace", "source_id", "source_record", "created_at"):
            self.assertEqual(current[key], imported[key])
        self.assertEqual(self.snapshot(), [[OWNER, "synthetic snapshot\n雪 ☃", True]])

    def test_fixed_transaction_rejects_payloads_that_bypass_renderer_validation(self):
        item_id = str(uuid.uuid4())
        valid = {"op": "create", "id": item_id, "data": {"kind": "inbox", "title": "Capture"}}
        invalid = [None, {}, [], [valid] * 21, [None],
                   [{**valid, "extra": "forbidden"}], [{**valid, "op": "import"}],
                   [{**valid, "data": {**valid["data"], "is_completed": True}}],
                   [{**valid, "data": {**valid["data"], "source_record": {}}}],
                   [{**valid, "data": {**valid["data"], "priority": True}}],
                   [{**valid, "data": {**valid["data"], "title": "\n\t "}}],
                   [{**valid, "data": {"title": "Missing kind"}}],
                   [{**valid, "data": {**valid["data"], "due": "2026-12-31"}}]]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.sql("TRUNCATE public.gtd_items, public.gtd_links, public.gtd_requests;")
                request_id = str(uuid.uuid4())
                query = self.cli("apply", str(self.request([valid], request_id)))
                encoded = base64.b64encode(json.dumps(payload).encode()).decode()
                query, replacements = re.subn(r"decode\('[A-Za-z0-9+/=]*', 'base64'\)",
                                              f"decode('{encoded}', 'base64')", query)
                self.assertEqual(replacements, 1)
                self.sql(query, ok=False)
                self.assertEqual(self.sql(self.cli("receipt", request_id))["status"], "missing")
                self.assertEqual(self.get(item_id)["status"], "missing")

    def test_stale_second_operation_rolls_back_the_batch_and_request(self):
        item_id, new_id, request_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        self.apply([{"op": "create", "id": item_id, "data": {"kind": "action", "title": "Step"}}])
        before = self.get(item_id)["item"]
        self.assertIn("revision conflict", self.apply([
            {"op": "create", "id": new_id, "data": {"kind": "inbox", "title": "Must roll back"}},
            {"op": "complete", "id": item_id, "expected_revision": 2},
        ], request_id, ok=False))
        self.assertEqual(self.get(new_id)["status"], "missing")
        self.assertEqual(self.get(item_id)["item"], before)
        self.assertEqual(self.sql(self.cli("receipt", request_id))["status"], "missing")
        self.assertEqual(self.sql(self.cli("read"))["request_count"], 1)

    def test_owner_kind_and_live_endpoint_guards_leave_state_unchanged(self):
        ids = {kind: str(uuid.uuid4()) for kind in ("action", "project", "inbox", "deleted", "foreign")}
        self.apply([{"op": "create", "id": ids[kind], "data": {
            "kind": "project" if kind == "deleted" else kind, "title": kind}}
                    for kind in ("action", "project", "inbox", "deleted")])
        self.apply([{"op": "delete", "id": ids["deleted"], "expected_revision": 1}])
        other_config = self.root / "other.json"
        other_config.write_text(json.dumps({"project_id": "synthetic-project", "owner_id": OTHER_OWNER}))
        self.apply([{"op": "create", "id": ids["foreign"], "data": {"kind": "project", "title": "Foreign"}}],
                   config=other_config)
        before = self.get(ids["action"])["item"]
        invalid = [
            {"op": "complete", "id": ids["foreign"], "expected_revision": 1},
            {"op": "patch", "id": ids["action"], "expected_revision": 1, "patch": {"kind": "project"}},
            {"op": "patch", "id": ids["project"], "expected_revision": 1, "patch": {"kind": "action"}},
        ]
        for target in ("action", "inbox", "deleted", "foreign"):
            invalid.append({"op": "link", "id": ids["action"], "expected_revision": 1, "project_id": ids[target]})
        invalid.extend([
            {"op": "link", "id": ids["inbox"], "expected_revision": 1, "project_id": ids["project"]},
            {"op": "link", "id": ids["deleted"], "expected_revision": 2, "project_id": ids["project"]},
        ])
        for operation in invalid:
            with self.subTest(operation=operation):
                self.apply([operation], ok=False)
                self.assertEqual(self.get(ids["action"])["item"], before)
                self.assertEqual(self.get(ids["action"])["links"], [])
        self.assertEqual(self.sql(self.cli("read"))["request_count"], 2)
        self.apply([{"op": "unlink", "id": ids["action"], "expected_revision": 1, "project_id": ids["project"]},
                    {"op": "complete", "id": ids["project"], "expected_revision": 1},
                    {"op": "link", "id": ids["action"], "expected_revision": 2, "project_id": ids["project"]}])
        self.assertTrue(self.get(ids["action"])["links"][0]["project_is_completed"])

    def while_locked(self, fixture_statement, queries):
        """Release a fixture lock only after every independent session waits on it."""
        blocker = subprocess.Popen(self.psql_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            blocker.stdin.write(f"BEGIN; {fixture_statement}; SELECT 'ready';\n")
            blocker.stdin.flush()
            self.assertTrue(select.select([blocker.stdout], [], [], 5)[0], "fixture lock timed out")
            self.assertEqual(blocker.stdout.readline().strip(), "ready")
            names = [f"gtd-race-{uuid.uuid4()}" for _ in queries]
            with ThreadPoolExecutor(max_workers=len(queries)) as executor:
                jobs = [executor.submit(subprocess.run, self.psql_command, input=query,
                                        text=True, capture_output=True, timeout=15,
                                        env={**os.environ, "PGAPPNAME": name})
                        for query, name in zip(queries, names)]
                try:
                    deadline = time.monotonic() + 5
                    names_sql = ",".join(f"'{name}'" for name in names)
                    while time.monotonic() < deadline:
                        waiting = self.sql(f"""SELECT to_jsonb(count(*)) FROM pg_stat_activity
                            WHERE application_name IN ({names_sql}) AND wait_event_type = 'Lock';""")
                        if waiting == len(queries):
                            break
                        time.sleep(0.02)
                    else:
                        self.fail("concurrent sessions did not reach the held lock")
                finally:
                    blocker.stdin.write("COMMIT;\n\\q\n")
                    blocker.stdin.flush()
                    blocker.communicate(timeout=5)
                return [job.result(timeout=20) for job in jobs]
        finally:
            if blocker.poll() is None:
                blocker.kill()
            blocker.communicate(timeout=5)

    def test_concurrent_requests_commit_once_and_revisions_have_one_winner(self):
        for exact_retry in (True, False):
            with self.subTest(exact_retry=exact_retry):
                item_id = str(uuid.uuid4())
                self.apply([{"op": "create", "id": item_id, "data": {"kind": "action", "title": "Concurrent"}}])
                request_id = str(uuid.uuid4())
                operation = {"op": "complete", "id": item_id, "expected_revision": 1}
                queries = [self.cli("apply", str(self.request([operation], request_id))),
                           self.cli("apply", str(self.request([operation], request_id if exact_retry else None)))]
                results = self.while_locked(
                    f"DO $lock$ BEGIN PERFORM id FROM public.gtd_items WHERE id='{item_id}' FOR UPDATE; END $lock$",
                    queries,
                )
                success = [json.loads(result.stdout.strip()) for result in results if result.returncode == 0]
                failure = [result.stderr for result in results if result.returncode != 0]
                if exact_retry:
                    self.assertEqual(len(success), 2, failure)
                    self.assertEqual(success[0], success[1])
                else:
                    self.assertEqual(len(success), 1, failure)
                    self.assertEqual(len(failure), 1)
                    self.assertIn("revision conflict", failure[0])
                self.assertEqual(self.get(item_id)["item"]["revision"], 2)

    def test_link_waits_for_concurrent_project_tombstone(self):
        action_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.apply([{"op": "create", "id": action_id, "data": {"kind": "action", "title": "Step"}},
                    {"op": "create", "id": project_id, "data": {"kind": "project", "title": "Outcome"}}])
        request_id = str(uuid.uuid4())
        query = self.cli("apply", str(self.request([
            {"op": "link", "id": action_id, "expected_revision": 1, "project_id": project_id}
        ], request_id)))
        result = self.while_locked(
            f"UPDATE public.gtd_items SET deleted_at=clock_timestamp() WHERE id='{project_id}'", [query]
        )[0]
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("owned live project missing", result.stderr)
        self.assertEqual(self.get(action_id)["item"]["revision"], 1)
        self.assertEqual(self.get(action_id)["links"], [])
        self.assertEqual(self.sql(self.cli("receipt", request_id))["status"], "missing")

    def test_new_deadlines_round_trip_without_converting_or_merging_imported_parts(self):
        item_id = str(uuid.uuid4())
        self.sql(f"""INSERT INTO public.gtd_items (id,owner_id,data)
            VALUES ('{item_id}','{OWNER}',
             '{{"kind":"action","title":"Deadline","due":{{"raw_components":{{"year":2026}}}},
                "start":{{"raw_components":{{"month":11}}}},"priority":0,"duration_label":null}}');""")
        for revision, value in enumerate((
            {"kind": "date_only", "date": "2026-12-31"},
            {"kind": "floating_datetime", "local": "2026-12-31T09:00:00"},
            {"kind": "zoned_datetime", "local": "2026-12-31T09:00:00", "time_zone": "America/New_York"},
            None,
        ), 1):
            self.apply([{"op": "patch", "id": item_id, "expected_revision": revision, "patch": {"due": value}}])
            data = self.get(item_id)["item"]["data"]
            self.assertEqual(data["due"], value)
            self.assertEqual(data["start"], {"raw_components": {"month": 11}})
            self.assertEqual(data["priority"], 0)
            self.assertIsNone(data["duration_label"])


if __name__ == "__main__":
    unittest.main()
