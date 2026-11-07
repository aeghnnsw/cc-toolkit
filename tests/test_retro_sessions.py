"""Exercise retrospective evidence through its command and generated files."""

import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import subprocess
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "retro_sessions.py"


class RetroSessionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.claude = self.base / "claude"
        self.codex = self.base / "codex"
        self.claude.mkdir()
        self.codex.mkdir()
        self.output = self.base / "evidence"

    def transcript(self, root, name, records, final_newline=True):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = "\n".join(json.dumps(record) for record in records)
        if final_newline:
            data += "\n"
        path.write_bytes(data.encode())
        return path

    def claude_message(self, text, **values):
        return {
            "type": "user", "timestamp": "2026-01-02T12:00:00Z",
            "cwd": str(self.repo), "message": {"role": "user", "content": text},
            **values,
        }

    def run_cli(self, *extra, roots=True, output=None):
        args = [sys.executable, str(SCRIPT), "--repo", str(self.repo),
                "--output", str(output or self.output)]
        if roots:
            args.extend(["--claude-root", str(self.claude),
                         "--codex-root", str(self.codex)])
        args.extend(extra)
        return subprocess.run(args, capture_output=True, text=True)

    def artifacts(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        manifest = json.loads(Path(summary["manifest"]).read_text())
        selected = [source for source in manifest["sources"] if source["selected"]]
        digests = [json.loads((self.output / source["digest"]).read_text())
                   for source in selected]
        return summary, manifest, selected, digests

    def run_in_process(self, *extra):
        args = [str(SCRIPT), "--repo", str(self.repo), "--output", str(self.output), *extra]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", args), redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(SCRIPT), run_name="__main__")
        return subprocess.CompletedProcess(args, stopped.exception.code, stdout.getvalue(), stderr.getvalue())

    def test_claude_message_has_exact_copy_and_source_line(self):
        source = self.transcript(self.claude, "project/session.jsonl", [
            self.claude_message("Inspect the contributor guide.")], final_newline=False)
        before = source.read_bytes()
        source.chmod(0o444)
        original_stat = source.stat()
        summary, manifest, selected, digests = self.artifacts(self.run_cli(
            "--through", "2026-01-03T00:00:00Z"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["selected_sources"], 1)
        self.assertEqual(manifest["counts"]["eligible_events"], 1)
        self.assertEqual((self.output / selected[0]["copy"]).read_bytes(), before)
        self.assertEqual(digests[0]["events"][0]["line"], 1)
        self.assertEqual(digests[0]["events"][0]["text"], "Inspect the contributor guide.")
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(source.stat().st_mtime_ns, original_stat.st_mtime_ns)

    def test_claude_auxiliary_state_does_not_create_false_timestamp_gaps(self):
        self.transcript(self.claude, "old-state.jsonl", [
            self.claude_message("Old context", timestamp="2026-01-01T00:00:00Z"),
            {"type": "atis-latch", "atis": {}},
            {"type": "api-request-blob", "hash": "fixture", "message": {"content": "Cached request"}},
            {"type": "ai-title", "aiTitle": "Fixture session"},
            {"type": "permission-mode", "permissionMode": "default"},
            {"type": "relocated", "relocatedCwd": str(self.repo)},
            {"type": "worktree-state", "worktreeSession": {}},
        ])
        message = self.claude_message("A real message with missing time")
        del message["timestamp"]
        self.transcript(self.claude, "missing-message-time.jsonl", [message])
        summary, manifest, selected, _ = self.artifacts(self.run_cli(
            "--after", "2026-01-02T00:00:00Z", "--through", "2026-01-03T00:00:00Z"))
        self.assertEqual(summary["selected_sources"], 1)
        self.assertEqual(summary["diagnostics"], 1)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(manifest["counts"]["ignored_records"], 6)
        self.assertEqual(selected[0]["diagnostics"], [{"code": "invalid_timestamp", "line": 1}])

    def test_resumed_mixed_repository_sessions_obey_current_cwd_and_time_window(self):
        foreign = str(self.base / "project-extra")
        self.transcript(self.claude, "mixed.jsonl", [
            self.claude_message("old", timestamp="2026-01-01T00:00:00Z"),
            self.claude_message("lower edge", timestamp="2026-01-02T07:00:00-05:00"),
            self.claude_message("inside", timestamp="2026-01-02T12:00:00.000001Z"),
            self.claude_message("foreign", cwd=foreign),
            self.claude_message("returned", timestamp="2026-01-02T12:00:01Z"),
            self.claude_message("later", timestamp="2026-01-02T12:00:01.000001Z"),
        ])
        self.transcript(self.codex, "year/resumed.jsonl", [
            {"type": "session_meta", "timestamp": "2025-12-01T00:00:00Z",
             "payload": {"cwd": foreign, "id": "synthetic-thread"}},
            {"type": "turn_context", "timestamp": "2026-01-02T11:00:00Z",
             "payload": {"cwd": str(self.repo)}},
            {"type": "response_item", "timestamp": "2026-01-02T12:00:00.500Z",
             "payload": {"type": "message", "role": "assistant", "content": [
                 {"type": "output_text", "text": "codex included"}]}},
            {"type": "turn_context", "payload": {"cwd": foreign}},
            {"type": "response_item", "timestamp": "2026-01-02T12:00:00.700Z",
             "payload": {"type": "message", "role": "assistant", "content": [
                 {"type": "output_text", "text": "codex excluded"}]}},
        ])
        _, manifest, _, digests = self.artifacts(self.run_cli(
            "--after", "2026-01-02T12:00:00Z", "--through", "2026-01-02T12:00:01Z"))
        events = [event for digest in digests for event in digest["events"]]
        self.assertEqual([event["text"] for event in events], ["inside", "returned", "codex included"])
        self.assertEqual([event["line"] for event in events], [3, 5, 3])
        self.assertEqual(manifest["window"]["after"], "2026-01-02T12:00:00Z")

    def test_tool_evidence_preserves_call_ids_and_nested_command_context(self):
        self.transcript(self.claude, "tools.jsonl", [
            self.claude_message([
                {"type": "text", "text": "check"},
                {"type": "tool_use", "id": "call-a", "name": "Read", "input": {"path": "guide.md"}},
                {"type": "thinking", "thinking": "private reasoning"}], type="assistant"),
            self.claude_message([{"type": "tool_result", "tool_use_id": "call-a", "content": [
                {"type": "text", "text": "guide contents"}]}]),
        ])
        records = [{"type": "session_meta", "payload": {"cwd": str(self.repo)}}]
        for payload in [
            {"type": "function_call", "name": "read_file", "call_id": "call-b", "arguments": '{"path":"guide.md"}'},
            {"type": "function_call_output", "call_id": "call-b", "output": "read completed"},
            {"type": "custom_tool_call", "name": "exec", "call_id": "call-c", "input": "await tools.shell()"},
            {"type": "custom_tool_call_output", "call_id": "call-c", "output": [{"type": "text", "text": "shell completed"}]},
            {"type": "reasoning", "summary": [{"text": "private reasoning"}]},
        ]:
            records.append({"type": "response_item", "timestamp": "2026-01-02T12:00:00Z", "payload": payload})
        records.extend([
            {"type": "event_msg", "timestamp": "2026-01-02T12:00:00Z", "payload": {
                "type": "item_completed", "item": {"type": "CommandExecution", "id": "nested-a",
                "command": ["git", "status"], "cwd": str(self.base / "other"),
                "status": "completed", "exit_code": 2, "aggregated_output": "command failed"}}},
            {"type": "event_msg", "timestamp": "2026-01-02T12:00:00Z", "payload": {
                "type": "agent_message", "message": "duplicate message"}},
            {"type": "response_item", "timestamp": "2026-01-02T12:00:00Z", "payload": {
                "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "still in repo"}]}},
        ])
        self.transcript(self.codex, "tools.jsonl", records)
        summary, _, _, digests = self.artifacts(self.run_cli("--through", "2026-01-03T00:00:00Z"))
        events = [event for digest in digests for event in digest["events"]]
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(len(events), 9)
        self.assertEqual([event["call_id"] for event in events if "call_id" in event],
                         ["call-a", "call-a", "call-b", "call-b", "call-c", "call-c", "nested-a"])
        command = next(event for event in events if event["kind"] == "command_execution")
        self.assertIn('"exit_code": 2', command["text"])
        self.assertIn("command failed", command["text"])
        self.assertIn(str(self.base / "other"), command["text"])
        self.assertEqual(events[-1]["cwd"], str(self.repo))
        self.assertNotIn("private reasoning", json.dumps(digests))
        self.assertNotIn("duplicate message", json.dumps(digests))

    def test_digest_limits_keep_head_and_tail_and_report_omissions(self):
        self.transcript(self.claude, "long.jsonl", [self.claude_message("x" * 350) for _ in range(65)])
        summary, manifest, _, digests = self.artifacts(self.run_cli("--through", "2026-01-03T00:00:00Z"))
        events = digests[0]["events"]
        self.assertEqual([events[0]["line"], events[29]["line"], events[30]["line"], events[-1]["line"]],
                         [1, 30, 36, 65])
        self.assertEqual(len(events), 60)
        self.assertEqual(events[0]["text"], "x" * 300)
        self.assertEqual(events[0]["omitted_characters"], 50)
        self.assertEqual(manifest["counts"]["clipped_characters"], 3000)
        self.assertEqual(summary["omitted_events"], 5)
        self.assertEqual(summary["status"], "ok")
        self.output = self.base / "shorter"
        _, _, _, digests = self.artifacts(self.run_cli(
            "--max-events", "3", "--max-text", "10", "--through", "2026-01-03T00:00:00Z"))
        self.assertEqual([event["line"] for event in digests[0]["events"]], [1, 2, 65])
        self.assertTrue(all(event["text"] == "x" * 10 for event in digests[0]["events"]))

    def test_damaged_and_unsupported_history_is_partial_with_physical_lines(self):
        source = self.transcript(self.claude, "damaged.jsonl", [
            {"type": "file-history-snapshot"},
            self.claude_message("usable"),
        ])
        with source.open("ab") as stream:
            stream.write(b'not json\n')
            stream.write((json.dumps(self.claude_message([
                {"type": "image", "source": {"data": "not displayed"}},
                {"type": "text", "text": "after damaged line"}])) + "\n").encode())
            stream.write((json.dumps(self.claude_message("no known time", timestamp="bad")) + "\n").encode())
            stream.write(b'{"unfinished":')
        self.transcript(self.claude, "unattributed.jsonl", [
            {"type": "user", "timestamp": "2026-01-02T12:00:00Z", "message": {"content": "unknown repo"}}])
        summary, manifest, selected, digests = self.artifacts(self.run_cli(
            "--through", "2026-01-03T00:00:00Z", "--codex-root", str(self.base / "missing")))
        self.assertEqual(summary["status"], "partial")
        self.assertEqual([event["line"] for event in digests[0]["events"]], [2, 4])
        self.assertEqual([(item["code"], item["line"]) for item in selected[0]["diagnostics"]],
                         [("malformed_json", 3), ("unsupported_content", 4), ("invalid_timestamp", 5),
                          ("incomplete_tail", 6)])
        self.assertEqual(selected[0]["counts"]["ignored_records"], 1)
        self.assertEqual(selected[0]["counts"]["unsupported_items"], 1)
        self.assertEqual({item["code"] for item in manifest["diagnostics"]},
                         {"missing_cwd", "root_unavailable"})
        self.assertEqual((self.output / selected[0]["copy"]).read_bytes(), source.read_bytes())
        self.assertNotIn("not displayed", json.dumps(digests))

    def test_git_worktrees_and_children_use_explicit_component_scope(self):
        main = self.repo
        message = self.base / "commit-message.txt"
        message.write_text("Initialize fixture\n")
        subprocess.run(["git", "-C", str(main), "-c", "user.name=Fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "--allow-empty", "-q", "-F", str(message)], check=True)
        external = self.base / "external worktree"
        subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "--detach", str(external)], check=True)
        self.transcript(self.claude, "parent.jsonl", [self.claude_message("main")])
        self.transcript(self.claude, "parent/subagents/local.jsonl", [
            self.claude_message("removed internal", cwd=str(main / "trees" / "removed"))])
        self.transcript(self.claude, "parent/subagents/external.jsonl", [
            self.claude_message("registered external", cwd=str(external))])
        self.transcript(self.claude, "parent/subagents/foreign.jsonl", [
            self.claude_message("explicit foreign", cwd=str(self.base / "project-extra"))])
        self.transcript(self.claude, "parent/subagents/missing.jsonl", [
            {"type": "user", "timestamp": "2026-01-02T12:00:00Z", "message": {"content": "no inherited cwd"}}])
        self.repo = external
        summary, manifest, _, digests = self.artifacts(self.run_cli("--through", "2026-01-03T00:00:00Z"))
        self.assertEqual(sorted(event["text"] for digest in digests for event in digest["events"]),
                         ["main", "registered external", "removed internal"])
        self.assertEqual(manifest["repository"]["main"], str(main))
        self.assertEqual(set(manifest["repository"]["roots"]), {str(main), str(external)})
        self.assertEqual(manifest["counts"]["skipped_sources"], 2)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(manifest["diagnostics"][0]["code"], "missing_cwd")

    def test_default_active_and_explicit_roots_are_isolated_and_deduplicated(self):
        fixture_home = self.base / "home"
        defaults = [fixture_home / ".claude" / "projects", fixture_home / ".codex" / "sessions"]
        active_claude = self.base / "active-claude"
        active_codex = self.base / "active-codex"
        for root in [*defaults, active_claude / "projects", active_codex / "sessions"]:
            root.mkdir(parents=True)
        for root, text in [(defaults[0], "default Claude"), (active_claude / "projects", "active Claude")]:
            self.transcript(root, "session.jsonl", [self.claude_message(text)])
        for root, text in [(defaults[1], "default Codex"), (active_codex / "sessions", "active Codex")]:
            self.transcript(root, "session.jsonl", [
                {"type": "session_meta", "payload": {"cwd": str(self.repo)}},
                {"type": "response_item", "timestamp": "2026-01-02T12:00:00Z", "payload": {
                    "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}}])
        class FixedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 1, 3, 0, 0, 0, 123456, tzinfo=timezone.utc)

        with patch.object(Path, "home", return_value=fixture_home), patch.dict(os.environ, {
                "CLAUDE_CONFIG_DIR": str(active_claude), "CODEX_HOME": str(active_codex)}), patch("datetime.datetime", FixedClock):
            _, manifest, _, digests = self.artifacts(self.run_in_process())
            self.assertEqual(len(digests), 4)
            self.assertEqual(manifest["window"]["through"], "2026-01-03T00:00:00.123+00:00")
            self.output = self.base / "explicit"
            alias = self.base / "alias"
            alias.symlink_to(defaults[1], target_is_directory=True)
            (defaults[1] / "duplicate.jsonl").symlink_to(defaults[1] / "session.jsonl")
            _, manifest, _, digests = self.artifacts(self.run_in_process(
                "--codex-root", str(defaults[1]), "--codex-root", str(alias)))
        self.assertEqual([event["text"] for digest in digests for event in digest["events"]], ["default Codex"])
        self.assertEqual(len(manifest["roots"]), 1)
        self.assertEqual(manifest["counts"]["candidate_sources"], 1)

    def test_invalid_arguments_and_output_paths_fail_without_changing_existing_files(self):
        existing = self.base / "existing"
        existing.mkdir()
        sentinel = existing / "keep.txt"
        sentinel.write_text("keep")
        alias = self.base / "source-alias"
        alias.symlink_to(self.claude, target_is_directory=True)
        cases = [
            (["--after", "2026-01-02T12:00:00"], self.output),
            (["--through", "bad"], self.output),
            (["--after", "2026-01-04T00:00:00Z", "--through", "2026-01-03T00:00:00Z"], self.output),
            (["--max-events", "0"], self.output),
            (["--max-text", "-1"], self.output),
            ([], existing), ([], self.claude / "output"), ([], alias / "output"),
            (["--repo", str(self.base)], self.output),
        ]
        for extra, output in cases:
            with self.subTest(extra=extra, output=output):
                result = self.run_cli(*extra, output=output)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(self.output.exists())
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertFalse((self.claude / "output").exists())

    def test_snapshot_excludes_appends_and_reports_truncation_or_replacement(self):
        original_open = Path.open
        for mutation in ("append", "truncate", "replace"):
            with self.subTest(mutation=mutation):
                source = self.transcript(self.claude, "changing.jsonl", [
                    self.claude_message("first"), self.claude_message("second")])
                initial = source.read_bytes()
                first_line = initial.index(b"\n") + 1
                self.output = self.base / mutation

                class ChangingStream:
                    def __init__(self, stream):
                        self.stream = stream
                        self.changed = False

                    def __getattr__(self, key):
                        return getattr(self.stream, key)

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return self.stream.__exit__(*args)

                    def read(self, size=-1):
                        if not self.changed:
                            self.changed = True
                            if mutation == "append":
                                with original_open(source, "ab") as stream:
                                    stream.write(b'{"type":"new appended record"}\n')
                            elif mutation == "truncate":
                                with original_open(source, "r+b") as stream:
                                    stream.truncate(first_line + 5)
                            else:
                                replacement = source.with_suffix(".replacement")
                                replacement.write_bytes(b'{"type":"replacement"}\n')
                                replacement.replace(source)
                        return self.stream.read(size)

                def changing_open(path, mode="r", *args, **kwargs):
                    stream = original_open(path, mode, *args, **kwargs)
                    return ChangingStream(stream) if path == source and mode == "rb" else stream

                with patch.object(Path, "open", changing_open):
                    summary, _, selected, _ = self.artifacts(self.run_in_process(
                        "--claude-root", str(self.claude), "--through", "2026-01-03T00:00:00Z"))
                self.assertEqual(selected[0]["boundary_bytes"], len(initial))
                expected = initial[:first_line + 5] if mutation == "truncate" else initial
                self.assertEqual((self.output / selected[0]["copy"]).read_bytes(), expected)
                codes = {item["code"] for item in selected[0]["diagnostics"]}
                if mutation == "append":
                    self.assertEqual(summary["status"], "ok")
                    self.assertEqual(codes, set())
                elif mutation == "truncate":
                    self.assertEqual(summary["status"], "partial")
                    self.assertTrue({"short_read", "source_truncated", "incomplete_tail"} <= codes)
                else:
                    self.assertEqual(summary["status"], "partial")
                    self.assertIn("source_replaced", codes)

    def test_fractional_precision_and_invalid_cwd_do_not_change_attribution(self):
        self.transcript(self.claude, "precise.jsonl", [
            self.claude_message("lower", timestamp="2026-01-02T12:00:00.000000001Z"),
            self.claude_message("upper", timestamp="2026-01-02T07:00:00.000000002-05:00"),
            self.claude_message("later", timestamp="2026-01-02T12:00:00.000000003Z"),
            self.claude_message("relative", cwd="project", timestamp="2026-01-02T12:00:00.000000002Z"),
            {"type": "user", "timestamp": "2026-01-02T12:00:00.000000002Z", "message": {"content": "must not inherit old cwd"}},
            self.claude_message("null cwd", cwd=None, timestamp="2026-01-02T12:00:00.000000002Z"),
        ])
        summary, manifest, selected, digests = self.artifacts(self.run_cli(
            "--after", "2026-01-02T12:00:00.000000001Z", "--through", "2026-01-02T12:00:00.000000002Z"))
        self.assertEqual([event["text"] for event in digests[0]["events"]], ["upper"])
        self.assertEqual(manifest["window"]["through"], "2026-01-02T12:00:00.000000002Z")
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(selected[0]["diagnostics"][0]["lines"], [4, 5, 6])
        self.assertEqual(selected[0]["diagnostics"][0]["count"], 3)

    def test_unknown_json_shapes_and_unreadable_sources_do_not_abort_available_evidence(self):
        denied = self.transcript(self.claude, "denied.jsonl", [self.claude_message("unreadable")])
        self.transcript(self.codex, "shapes.jsonl", [
            {"type": "session_meta", "payload": {"cwd": str(self.repo)}},
            {"type": "response_item", "timestamp": "2026-01-02T12:00:00Z", "payload": {
                "type": "message", "role": "assistant", "content": [
                    None, {"type": []}, {"type": "output_text", "text": {"not": "text"}},
                    {"type": "output_text", "text": "usable"}]}},
            {"type": [], "timestamp": "2026-01-02T12:00:00Z"},
            {"type": "response_item", "timestamp": "2026-01-02T12:00:00Z", "payload": []},
            {"type": "event_msg", "timestamp": "2026-01-02T12:00:00Z", "payload": {
                "type": "item_completed", "item": {"type": "FileChange", "changes": []}}},
            {"type": "response_item", "timestamp": "2026-01-02T12:00:00Z", "payload": {
                "type": "function_call", "name": {"nested": "x" * 500}, "call_id": "x" * 500,
                "arguments": {"nested": "x" * 500}}},
        ])
        original_open = Path.open
        def protected_open(path, mode="r", *args, **kwargs):
            if path == denied and mode == "rb":
                raise PermissionError("synthetic read denial")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", protected_open):
            summary, manifest, selected, digests = self.artifacts(self.run_in_process(
                "--claude-root", str(self.claude), "--codex-root", str(self.codex),
                "--max-text", "20", "--through", "2026-01-03T00:00:00Z"))
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(manifest["diagnostics"][0]["code"], "source_unavailable")
        self.assertEqual(selected[0]["counts"]["unsupported_items"], 6)
        self.assertEqual(digests[0]["events"][0]["text"], "usable")
        call = digests[0]["events"][1]
        self.assertEqual(len(call["text"]), 20)
        self.assertEqual(len(call["tool"]), 20)
        self.assertEqual(call["metadata_omitted_characters"]["call_id"], 480)

    def test_repeated_history_gaps_keep_exact_counts_and_bounded_line_samples(self):
        self.transcript(self.claude, "unknown.jsonl", [self.claude_message("available")] + [
            self.claude_message([{"type": "unknown-block"}]) for _ in range(100)])
        self.transcript(self.claude, "unattributed.jsonl", [
            {"type": "user", "timestamp": "2026-01-02T12:00:00Z", "message": {"content": "missing cwd"}}
            for _ in range(200)])
        self.transcript(self.claude, "foreign.jsonl", [
            self.claude_message("foreign", cwd=str(self.base / "other")) for _ in range(50)])
        summary, manifest, selected, digests = self.artifacts(self.run_cli("--through", "2026-01-03T00:00:00Z"))
        self.assertEqual(summary["diagnostics"], 300)
        self.assertEqual(manifest["counts"]["foreign_records"], 50)
        self.assertEqual(manifest["counts"]["unattributed_records"], 200)
        self.assertEqual(len(selected[0]["diagnostics"]), 1)
        diagnostic = digests[0]["diagnostics"][0]
        self.assertEqual(diagnostic["count"], 100)
        self.assertEqual(diagnostic["lines"], list(range(2, 22)))
        self.assertEqual(diagnostic["omitted_line_references"], 80)
        self.assertEqual(len(manifest["diagnostics"]), 1)
        self.assertEqual(manifest["diagnostics"][0]["count"], 200)


if __name__ == "__main__":
    unittest.main()
