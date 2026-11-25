"""Command-line checks for the live worktree script that repo-cleanup runs.

Each check builds a temporary Git repository with worktrees, adds evidence of a
live session (a process, a session log, or a lock), and reads the lines that
the script prints. No check touches another repository.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "live_worktrees.py"


def write_log(path: Path, records: list[dict], age_minutes: float = 0) -> Path:
    """Write a JSONL session log and set its change time age_minutes ago."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    stamp = time.time() - age_minutes * 60
    os.utime(path, (stamp, stamp))
    return path


def agy_time(age_minutes: float) -> str:
    """Return a last_modified_time value age_minutes ago, in the form that Antigravity writes."""
    stamp = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    return f"{stamp:%Y-%m-%d %H:%M:%S}.{stamp.microsecond:06d}"[:-1] + "+00:00"  # A 5-digit fraction.


@unittest.skipUnless(shutil.which("lsof") and shutil.which("git"), "needs lsof and git")
class LiveWorktreesTests(unittest.TestCase):
    def setUp(self):
        # mkdtemp is under a symlink on macOS (/var -> /private/var), so the
        # checks also cover paths that lsof reports in resolved form.
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.claude_dir = self.tmp / "claude-config"
        self.codex_dir = self.tmp / "codex-home"
        for folder in (self.home, self.claude_dir, self.codex_dir):
            folder.mkdir()
        (self.tmp / "gitconfig").write_text("")
        self.env = {
            key: value for key, value in os.environ.items()
            if key not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")
        }
        self.env.update(
            HOME=str(self.home),
            CLAUDE_CONFIG_DIR=str(self.claude_dir),
            CODEX_HOME=str(self.codex_dir),
            GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
        )
        self.repo = self.tmp / "repo"
        self.git("init", "-q", "-b", "master", str(self.repo), cwd=self.tmp)
        (self.repo / "README").write_text("x\n")
        self.git("add", "README")
        self.git("commit", "-q", "-m", "init")

    def git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd or self.repo, env=self.env,
            capture_output=True, text=True, check=True,
        )
        return result.stdout

    def add_worktree(self, name: str, parent: Path | None = None) -> Path:
        path = (parent or self.tmp) / name
        self.git("worktree", "add", "-q", "-b", name, str(path))
        return path

    def listed_path(self, worktree: Path) -> str:
        """Return the worktree path as `git worktree list` prints it."""
        for line in self.git("worktree", "list", "--porcelain").splitlines():
            if line.startswith("worktree ") and os.path.samefile(line[9:], worktree):
                return line[9:]
        self.fail(f"{worktree} is not a worktree")

    def start(self, cwd: Path, env: dict[str, str] | None = None,
              command: list[str] | None = None) -> subprocess.Popen:
        proc = subprocess.Popen(command or ["sleep", "60"], cwd=cwd, env=env or self.env)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        return proc

    def run_script(self, cwd: Path | None = None, shell: bool = False) -> dict[str, str]:
        """Return {worktree path: evidence} from a run that must succeed."""
        return {path: evidence for path, (evidence, _) in self.run_fields(cwd, shell).items()}

    def run_fields(self, cwd: Path | None = None, shell: bool = False) -> dict[str, tuple[str, str]]:
        """Return {worktree path: (evidence, window end)}; each line must have three fields."""
        command = [sys.executable, str(SCRIPT), "--repo", str(self.repo)]
        if shell:
            # The trailing `:` keeps sh from replacing itself with the script.
            command = ["sh", "-c", '"$@"; :', "sh", *command]
        result = subprocess.run(
            command, cwd=cwd or self.repo, env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = {}
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            self.assertEqual(len(fields), 3, line)
            listed[fields[0]] = (fields[1], fields[2])
        return listed

    def test_lists_a_worktree_with_a_process_inside_and_skips_an_idle_one(self):
        busy = self.add_worktree("busy")
        idle = self.add_worktree("idle")
        (busy / "sub").mkdir()
        proc = self.start(busy / "sub")

        listed = self.run_script()

        self.assertIn(f"process {proc.pid} (sleep)", listed[self.listed_path(busy)])
        self.assertNotIn(self.listed_path(idle), listed)

    def test_lists_a_worktree_from_a_recent_claude_log_and_skips_an_old_one(self):
        recent = self.add_worktree("recent")
        old = self.add_worktree("old")
        # A Claude Code session that started in the main checkout records the
        # worktree as its cwd after it moves there.
        recent_log = write_log(self.claude_dir / "projects" / "-repo" / "s1.jsonl", [
            {"type": "user", "cwd": str(self.repo)},
            {"type": "assistant", "cwd": str(recent / "src")},
        ])
        write_log(self.claude_dir / "projects" / "-repo" / "s2.jsonl",
                  [{"type": "user", "cwd": str(old)}], age_minutes=90)

        listed = self.run_script()

        self.assertIn(f"session log {recent_log.resolve()}", listed[self.listed_path(recent)])
        self.assertNotIn(self.listed_path(old), listed)

    def test_lists_a_worktree_from_a_recent_codex_rollout_and_skips_an_old_one(self):
        worktree = self.add_worktree("codex-run")
        old = self.add_worktree("codex-old")
        day = self.codex_dir / "sessions" / "2026" / "11" / "18"
        rollout = write_log(day / "rollout-2026-11-18T09-00-00-t1.jsonl", [
            {"type": "session_meta", "payload": {"id": "t1", "cwd": str(self.repo)}},
            {"type": "turn_context", "payload": {"cwd": str(worktree)}},
        ])
        write_log(day / "rollout-2026-11-18T07-00-00-t2.jsonl",
                  [{"type": "session_meta", "payload": {"id": "t2", "cwd": str(old)}}], age_minutes=90)

        listed = self.run_script()

        self.assertIn(f"session log {rollout.resolve()}", listed[self.listed_path(worktree)])
        self.assertNotIn(self.listed_path(old), listed)

    def agy_database(self, folder: Path, rows: list[tuple]) -> Path:
        """Write conversation_summaries.db with the rows kept in the write-ahead log, as in a live database."""
        folder.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(folder / "conversation_summaries.db")
        self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE conversation_summaries (conversation_id text, "
                           "last_modified_time datetime NOT NULL, workspace_uris text NOT NULL)")
        connection.executemany("INSERT INTO conversation_summaries VALUES (?, ?, ?)", rows)
        connection.commit()
        return folder

    def test_lists_a_worktree_from_a_recent_antigravity_conversation_and_skips_an_old_one(self):
        cli = self.add_worktree("agy-cli", parent=self.tmp / "with space")  # The file URI holds %20.
        t3 = self.add_worktree("agy-t3")
        old = self.add_worktree("agy-old")
        cli_dir = self.agy_database(self.home / ".gemini" / "antigravity-cli", [
            ("conv-cli", agy_time(5), json.dumps([(cli / "src").as_uri(), "vscode-remote://host/x"])),
            ("conv-old", agy_time(90), json.dumps([old.as_uri()])),
            ("conv-main", agy_time(1), json.dumps([self.repo.as_uri()])),
        ])
        profile_dir = self.agy_database(
            self.home / ".t3" / "userdata" / "providers" / "antigravity" / "0f3a" / "antigravity-acp",
            [("conv-t3", agy_time(2).replace(" ", "T").replace("+00:00", "Z"), json.dumps([t3.as_uri()]))])
        originals = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                     for folder in (cli_dir, profile_dir) for path in folder.iterdir()}
        self.assertIn(cli_dir / "conversation_summaries.db-wal", originals)

        listed = self.run_script()

        self.assertRegex(listed[self.listed_path(cli)],
                         rf"^Antigravity conversation conv-cli in {re.escape(str(cli_dir))} \([45] min ago\)$")
        self.assertRegex(listed[self.listed_path(t3)],
                         rf"^Antigravity conversation conv-t3 in {re.escape(str(profile_dir))} \([12] min ago\)$")
        self.assertNotIn(self.listed_path(old), listed)
        self.assertEqual(set(listed), {self.listed_path(cli), self.listed_path(t3)})
        self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns) for path in originals}, originals)

    def test_antigravity_time_that_cannot_be_read_lists_the_worktree(self):
        worktree = self.add_worktree("agy-unknown")
        self.agy_database(self.home / ".gemini" / "antigravity", [
            ("conv-x", "yesterday", json.dumps([worktree.as_uri()])),
            ("conv-bad-old", agy_time(120), "not json"),  # Outside the window, so never parsed.
        ])

        listed = self.run_script()

        self.assertIn("Antigravity conversation conv-x", listed[self.listed_path(worktree)])
        self.assertIn("(time unknown)", listed[self.listed_path(worktree)])

    @unittest.skipIf(os.geteuid() == 0, "root ignores folder permissions")
    def test_fails_when_antigravity_data_cannot_be_read(self):
        worktree = self.add_worktree("agy-fail")
        uri = json.dumps([worktree.as_uri()])

        def garbage(home):
            folder = home / ".gemini" / "antigravity-cli"
            folder.mkdir(parents=True)
            (folder / "conversation_summaries.db").write_bytes(b"not a database")

        def locked(folder):
            folder.chmod(0)
            self.addCleanup(folder.chmod, 0o755)

        cases = [
            ("cannot read the Antigravity database", garbage),
            # A live conversation in a folder that cannot be searched is not skipped.
            ("cannot read the Antigravity database", lambda home: locked(
                self.agy_database(home / ".gemini" / "antigravity-cli", [("conv-1", agy_time(3), uri)]))),
            ("cannot list the T3 Code Antigravity profiles", lambda home: locked(
                (self.agy_database(home / ".t3" / "userdata" / "providers" / "antigravity" / "0f3a" / "antigravity-acp",
                                   [("conv-2", agy_time(3), uri)])).parents[1])),
            ("cannot read workspace_uris of Antigravity conversation conv-3", lambda home: self.agy_database(
                home / ".gemini" / "antigravity", [("conv-3", agy_time(3), "not json")])),
            ("cannot read workspace_uris of Antigravity conversation conv-4", lambda home: self.agy_database(
                home / ".gemini" / "antigravity", [("conv-4", agy_time(3), json.dumps([{"uri": worktree.as_uri()}]))])),
            ("cannot read workspace_uris of Antigravity conversation conv-5", lambda home: self.agy_database(
                home / ".gemini" / "antigravity", [("conv-5", agy_time(3), json.dumps([str(worktree)]))])),
        ]
        for index, (message, make) in enumerate(cases):
            with self.subTest(index=index, message=message):
                home = self.tmp / f"home-{index}"  # Each case has its own home folder.
                make(home)

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--repo", str(self.repo)],
                    env=dict(self.env, HOME=str(home)), capture_output=True, text=True,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn(f"live_worktrees: {message}", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_gives_the_window_end_only_when_logs_and_conversations_alone_list_a_worktree(self):
        logs = self.add_worktree("logs-only")
        mixed = self.add_worktree("log-and-agy")
        busy = self.add_worktree("log-and-process")
        unknown = self.add_worktree("agy-time-unknown")
        projects = self.claude_dir / "projects" / "-repo"
        newest = write_log(projects / "s5.jsonl", [{"cwd": str(logs)}], age_minutes=10)
        write_log(projects / "s6.jsonl", [{"cwd": str(logs)}], age_minutes=30)
        write_log(projects / "s7.jsonl", [{"cwd": str(mixed)}], age_minutes=40)
        write_log(projects / "s8.jsonl", [{"cwd": str(busy)}], age_minutes=5)
        self.start(busy)
        # The conversation is newer than the log of mixed, so its time sets the end.
        changed = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
        self.agy_database(self.home / ".gemini" / "antigravity", [
            ("conv-new", f"{changed:%Y-%m-%d %H:%M:%S}.12345+00:00", json.dumps([mixed.as_uri()])),
            ("conv-x", "yesterday", json.dumps([unknown.as_uri()])),
        ])

        def end(stamp: float) -> str:
            # The first whole second after the window: the plan keeps the worktree up to its end.
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(stamp + 3600) + 1))

        listed = self.run_fields()

        self.assertEqual(listed[self.listed_path(logs)][1], end(newest.stat().st_mtime))
        self.assertIn("and 1 more", listed[self.listed_path(logs)][0])
        self.assertEqual(listed[self.listed_path(mixed)][1], end(changed.timestamp()))
        self.assertIn("process", listed[self.listed_path(busy)][0])
        self.assertEqual(listed[self.listed_path(busy)][1], "")
        self.assertEqual(listed[self.listed_path(unknown)][1], "unknown")

    def test_reads_the_config_folder_of_another_running_session(self):
        worktree = self.add_worktree("other-config")
        other = self.tmp / "other-claude-config"
        log = write_log(other / "projects" / "-repo" / "s3.jsonl", [{"cwd": str(worktree)}])
        # Only the environment of this process names the other folder. macOS
        # hides the environment of platform binaries such as /bin/sleep.
        self.start(self.tmp, env=dict(self.env, CLAUDE_CONFIG_DIR=str(other)),
                   command=[sys.executable, "-c", "import time; time.sleep(60)"])

        listed = self.run_script()

        self.assertIn(f"session log {log.resolve()}", listed[self.listed_path(worktree)])

    def test_leaves_out_the_logs_and_processes_of_the_current_session(self):
        claude_run = self.add_worktree("own-claude")
        codex_run = self.add_worktree("own-codex")
        self.env.update(CLAUDE_CODE_SESSION_ID="own-session-1", CODEX_THREAD_ID="own-thread-9")
        projects = self.claude_dir / "projects" / "-repo"
        write_log(projects / "own-session-1.jsonl", [{"cwd": str(claude_run)}])
        write_log(projects / "own-session-1" / "subagents" / "agent-a.jsonl", [{"cwd": str(claude_run)}])
        write_log(self.codex_dir / "sessions" / "rollout-2026-11-18T09-00-00-own-thread-9.jsonl",
                  [{"type": "session_meta", "payload": {"cwd": str(codex_run)}}])

        # The shell that runs the script stands for the current session.
        listed = self.run_script(cwd=claude_run, shell=True)

        self.assertNotIn(self.listed_path(claude_run), listed)
        self.assertNotIn(self.listed_path(codex_run), listed)

    def test_lists_a_locked_worktree_with_its_reason(self):
        with_reason = self.add_worktree("locked-reason")
        bare = self.add_worktree("locked-bare")
        self.git("worktree", "lock", "--reason", "session 42 runs here", str(with_reason))
        self.git("worktree", "lock", str(bare))

        listed = self.run_script()

        self.assertIn("locked: session 42 runs here", listed[self.listed_path(with_reason)])
        self.assertIn("locked", listed[self.listed_path(bare)])

    def test_gives_a_path_to_the_deepest_worktree_and_never_lists_the_main_one(self):
        nested = self.add_worktree("nested", parent=self.repo / "trees")
        main_only = self.add_worktree("main-only", parent=self.repo / "trees")
        write_log(self.claude_dir / "projects" / "-repo" / "s4.jsonl", [
            {"cwd": str(self.repo)},
            {"cwd": str(nested / "src")},
        ])
        self.start(self.repo)

        listed = self.run_script()

        self.assertEqual(set(listed), {self.listed_path(nested)})
        self.assertNotIn(self.listed_path(main_only), listed)

    def test_names_one_process_and_counts_the_others(self):
        busy = self.add_worktree("crowded")
        first = self.start(busy)
        second = self.start(busy)

        listed = self.run_script()

        line = listed[self.listed_path(busy)]
        self.assertRegex(line, rf"^process ({first.pid}|{second.pid}) \(sleep\) and 1 more$")

    def test_fails_when_ps_fails(self):
        # Without ps, the config folders of other sessions stay unknown, so a
        # result would miss their logs.
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake_ps = bin_dir / "ps"
        fake_ps.write_text("#!/bin/sh\necho 'ps: broken' >&2\nexit 1\n")
        fake_ps.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}{os.pathsep}{self.env['PATH']}"

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo)],
            env=self.env, capture_output=True, text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ps: broken", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_fails_outside_a_repository(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.home)],
            env=self.env, capture_output=True, text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("live_worktrees:", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
