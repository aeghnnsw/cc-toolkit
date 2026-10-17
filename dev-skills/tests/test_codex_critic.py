"""Command-line checks for the pressure-test Codex critic runner.

Each test runs the runner with a fake `codex` executable first on PATH. A
scenario file tells the fake what to print, what reply to write, how long to
sleep, and which exit code to return. The fake records its argv, working
directory, stdin, and process ID so the tests can check each call.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "pressure-test" / "SKILL.md"
SCRIPT = SKILL.parent / "scripts" / "codex_critic.py"
ALLOWED_MODELS = json.loads((PLUGIN_ROOT.parent / "allowed-models.json").read_text(encoding="utf-8"))
CRITIC_MODEL = ALLOWED_MODELS["gpt"]["primary"]
PROMPT = "GOAL:\nShip the runner.\n"
CRITIC = "\nYou are an independent adversarial critic.\n"
THREAD_ID = "0199a7b2-thread"
STALE_REPLY = "stale reply from an earlier round"
SLEEPER = "import time; time.sleep(30)"
# A detached child that keeps starting grandchildren and lists their IDs in a file.
FORKER = """\
import subprocess, sys, time
while True:
    pid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]).pid
    with open({forks!r}, "a") as handle:
        handle.write(f"{{pid}}\\n")
    time.sleep(0.01)
"""

# A slow `ps` that adds a new descendant of the fake codex on every call, so a
# cleanup scan never runs out of new processes. The IDs are above the macOS
# PID limit, so signals to them fail with ProcessLookupError.
SLOW_PS = """\
import json, os, subprocess, sys, time

time.sleep(0.5)
sys.stdout.write(subprocess.run(["/bin/ps", *sys.argv[1:]], capture_output=True, text=True).stdout)
count = os.environ["SLOW_PS_COUNT"]
calls = int(open(count).read()) if os.path.exists(count) else 0
open(count, "w").write(str(calls + 1))
if os.path.exists(os.environ["SLOW_PS_RECORD"]):
    print(900000 + calls, json.load(open(os.environ["SLOW_PS_RECORD"]))["pid"])
"""

FAKE_CODEX = """\
import json, os, subprocess, sys, time

scenario = json.load(open(os.environ["FAKE_CODEX_SCENARIO"], encoding="utf-8"))
child = None
if scenario["child"]:  # like a Codex shell tool call: a child in its own session
    child = subprocess.Popen([sys.executable, "-c", scenario["child"]], start_new_session=True).pid
with open(scenario["record"], "w", encoding="utf-8") as handle:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": sys.stdin.read(), "pid": os.getpid(),
               "child": child}, handle)
time.sleep(scenario["sleep"])
for event in scenario["events"]:
    print(event if isinstance(event, str) else json.dumps(event))
sys.stderr.write(scenario["stderr"])
if scenario["reply"] is not None:
    with open(sys.argv[sys.argv.index("-o") + 1], "w", encoding="utf-8") as handle:
        handle.write(scenario["reply"])
sys.exit(scenario["exit"])
"""


def gone(pid: int, wait: float = 3.0) -> bool:
    """Return True when the process ends within the wait (init reaps a killed orphan)."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def kill_quietly(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class CodexCriticTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve()
        self.repo, self.workdir, self.bin = root / "repo", root / "work", root / "bin"
        for path in (self.repo, self.workdir, self.bin):
            path.mkdir()
        self.scenario, self.record = root / "scenario.json", root / "record.json"
        self.install_fake("codex", FAKE_CODEX)
        self.write_inputs()

    def install_fake(self, name: str, source: str) -> None:
        """Put an executable Python script named name first on the runner's PATH."""
        fake = self.bin / name
        fake.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
        fake.chmod(0o755)

    def write_inputs(self) -> None:
        """Write the repo, model, prompt.md, and critic.txt inputs."""
        self.write("repo", f"{self.repo}\n")
        self.write("model", f"{CRITIC_MODEL}\n")
        self.write("prompt.md", PROMPT)
        self.write("critic.txt", CRITIC)

    def write(self, name: str, text: str) -> None:
        (self.workdir / name).write_text(text, encoding="utf-8")

    def run_critic(self, mode: str, *, timeout: float | None = None, path: str | None = None,
                   env: dict[str, str] | None = None, **scenario) -> tuple[int, str]:
        """Run the runner against the fake codex; return its exit code and its stdout line."""
        settings = {"events": [], "stderr": "", "reply": None, "exit": 0, "sleep": 0, "child": None}
        settings.update(scenario, record=str(self.record))
        self.record.unlink(missing_ok=True)
        self.scenario.write_text(json.dumps(settings), encoding="utf-8")
        env = dict(os.environ, **(env or {}), FAKE_CODEX_SCENARIO=str(self.scenario))
        env["PATH"] = path if path is not None else f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}"
        if timeout is not None:
            self.write("timeout", f"{timeout}\n")
        command = [sys.executable, str(SCRIPT), mode, str(self.workdir)]
        completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        return completed.returncode, completed.stdout.strip()

    def call(self) -> dict:
        """Return the argv, cwd, stdin, pid, and child pid that the fake codex recorded."""
        return json.loads(self.record.read_text(encoding="utf-8"))

    def test_kickoff_sends_the_prompt_read_only_from_the_repo_and_saves_the_thread_id(self):
        events = [{"type": "thread.started", "thread_id": THREAD_ID}, {"type": "turn.completed"}]
        code, line = self.run_critic("kickoff", events=events, reply="The weakest point is X.")
        self.assertEqual((code, line), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        call = self.call()
        self.assertEqual(call["argv"], [
            "exec", "--json", "--skip-git-repo-check", "-m", CRITIC_MODEL,
            "-c", 'model_reasoning_effort="xhigh"', "-s", "read-only", "-C", str(self.repo),
            "-o", str(self.workdir / "msg.txt"), "-",
        ])
        self.assertEqual(call["cwd"], str(self.repo))
        self.assertEqual(call["stdin"], PROMPT + CRITIC)
        self.assertEqual((self.workdir / "thread_id").read_text(encoding="utf-8"), THREAD_ID)

    def test_kickoff_without_critic_text_sends_the_prompt_alone(self):
        (self.workdir / "critic.txt").unlink()
        events = [{"type": "thread.started", "thread_id": THREAD_ID}]
        self.assertEqual(self.run_critic("kickoff", events=events, reply="objection"),
                         (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertEqual(self.call()["stdin"], PROMPT)

    def test_resume_passes_the_thread_id_and_the_sandbox_as_config_from_the_repo(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        code, line = self.run_critic("resume", reply="NO SUBSTANTIVE OBJECTION.")
        self.assertEqual((code, line), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        call = self.call()
        self.assertEqual(call["argv"], [
            "exec", "resume", THREAD_ID, "--json", "--skip-git-repo-check", "-m", CRITIC_MODEL,
            "-c", 'model_reasoning_effort="xhigh"', "-c", 'sandbox_mode="read-only"',
            "-o", str(self.workdir / "msg.txt"), "-",
        ])
        self.assertNotIn("-s", call["argv"])
        self.assertNotIn("-C", call["argv"])
        self.assertEqual(call["cwd"], str(self.repo))
        self.assertEqual(call["stdin"], PROMPT + CRITIC)

    def test_smoke_uses_low_effort_and_checks_the_reply(self):
        for reply, code, status in (("ok", 0, "ok"), ("nope", 1, "error:smoke reply")):
            with self.subTest(reply=reply):
                self.assertEqual(self.run_critic("smoke", reply=reply),
                                 (code, f"exit=0 model={CRITIC_MODEL} status={status}"))
                call = self.call()
                self.assertEqual(call["argv"], [
                    "exec", "--json", "--skip-git-repo-check", "-m", CRITIC_MODEL,
                    "-c", 'model_reasoning_effort="low"', "-s", "read-only", "-C", str(self.repo),
                    "-o", str(self.workdir / "msg.txt"), "Reply with exactly: ok",
                ])
                self.assertEqual(call["cwd"], str(self.repo))
                self.assertEqual(call["stdin"], "")

    def test_flag_in_an_error_event_or_error_item_is_flagged_even_when_codex_fails(self):
        message = "This request has been flagged for possible cybersecurity risk."
        events = {
            "error event": {"type": "error", "message": message},
            "turn.failed event": {"type": "turn.failed", "error": {"message": "cyber_policy"}},
            "non-JSON error line": '{"type": "error", "message": "' + message,
            "error item": {"type": "item.completed",
                           "item": {"type": "error", "message": "Your request was rerouted as a fallback."}},
        }
        for name, event in events.items():
            with self.subTest(name):
                self.assertEqual(self.run_critic("kickoff", events=[event], exit=1),
                                 (1, f"exit=1 model={CRITIC_MODEL} status=flagged"))

    def test_reroute_notice_in_stderr_is_flagged(self):
        events = [{"type": "thread.started", "thread_id": THREAD_ID}]
        code, line = self.run_critic("kickoff", events=events, reply="objection",
                                     stderr=f"model rerouted: {CRITIC_MODEL} -> other\n")
        self.assertEqual((code, line), (1, f"exit=0 model={CRITIC_MODEL} status=flagged"))

    def test_flag_words_in_the_critic_reply_are_not_a_flag(self):
        words = "The plan was flagged for review; skipping it is a policy violation."
        events = [
            {"type": "thread.started", "thread_id": THREAD_ID},
            {"type": "item.completed", "item": {"type": "agent_message", "text": words}},
            {"type": "turn.completed"},
        ]
        self.assertEqual(self.run_critic("kickoff", events=events, reply=words),
                         (0, f"exit=0 model={CRITIC_MODEL} status=ok"))

    def test_non_zero_exit_is_an_error(self):
        events = [{"type": "thread.started", "thread_id": THREAD_ID}]
        self.assertEqual(self.run_critic("kickoff", events=events, reply="partial", stderr="boom\n", exit=3),
                         (1, f"exit=3 model={CRITIC_MODEL} status=error:exit 3"))

    def test_timeout_kills_the_call_and_reports_exit_124(self):
        started = time.monotonic()
        result = self.run_critic("kickoff", timeout=1, sleep=5, reply="late reply")
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        with self.assertRaises(ProcessLookupError):  # the runner killed the call; it did not leave it running
            os.kill(self.call()["pid"], 0)

    def test_timeout_also_kills_children_in_their_own_session(self):
        result = self.run_critic("kickoff", timeout=1, sleep=5, child=SLEEPER)
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        child = self.call()["child"]
        self.addCleanup(kill_quietly, child)
        self.assertTrue(gone(child), "a child in its own session survived the timeout")

    def test_timeout_kills_grandchildren_that_a_detached_child_keeps_starting(self):
        forks = self.workdir.parent / "grandchildren.txt"
        result = self.run_critic("kickoff", timeout=1, sleep=5, child=FORKER.format(forks=str(forks)))
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        child = self.call()["child"]
        self.addCleanup(kill_quietly, child)
        self.assertTrue(gone(child))
        time.sleep(0.2)  # a surviving child would keep adding IDs
        grandchildren = [int(line) for line in forks.read_text(encoding="utf-8").split()]
        for pid in grandchildren:
            self.addCleanup(kill_quietly, pid)
        self.assertTrue(grandchildren)
        self.assertEqual([pid for pid in grandchildren if not gone(pid, wait=1)], [])

    def test_timeout_cleanup_ends_within_its_deadline_when_scans_are_slow(self):
        self.install_fake("ps", SLOW_PS)
        env = {"SLOW_PS_COUNT": str(self.workdir.parent / "ps_calls"), "SLOW_PS_RECORD": str(self.record)}
        started = time.monotonic()
        result = self.run_critic("kickoff", timeout=1, sleep=30, env=env)
        elapsed = time.monotonic() - started
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        self.assertLess(elapsed, 1 + 5 + 2.5, "cleanup ran past its 5-second deadline")
        self.assertTrue(gone(self.call()["pid"], wait=1), "codex survived the timeout")

    def test_kickoff_without_a_thread_id_is_an_error(self):
        self.write("thread_id", "id-from-an-earlier-session\n")
        self.assertEqual(self.run_critic("kickoff", events=[{"type": "turn.completed"}], reply="objection"),
                         (1, f"exit=0 model={CRITIC_MODEL} status=error:no thread id"))
        self.assertEqual((self.workdir / "thread_id").read_text(encoding="utf-8"), "")
        self.assertNotIn("--last", self.call()["argv"])

    def test_stale_reply_is_deleted_before_a_failing_call(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        self.write("msg.txt", STALE_REPLY)
        self.assertEqual(self.run_critic("resume", exit=1),
                         (1, f"exit=1 model={CRITIC_MODEL} status=error:exit 1"))
        self.assertFalse((self.workdir / "msg.txt").exists())

    def test_exit_zero_without_a_reply_is_an_error(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        for reply in (None, "  \n"):
            with self.subTest(reply=reply):
                self.write("msg.txt", STALE_REPLY)
                self.assertEqual(self.run_critic("resume", reply=reply),
                                 (1, f"exit=0 model={CRITIC_MODEL} status=error:no reply"))

    def test_resume_without_a_thread_id_does_not_call_codex(self):
        self.write("msg.txt", STALE_REPLY)
        self.assertEqual(self.run_critic("resume", reply="objection"),
                         (1, f"exit=2 model={CRITIC_MODEL} status=error:missing thread_id"))
        self.assertFalse(self.record.exists())
        self.assertFalse((self.workdir / "msg.txt").exists())

    def test_missing_or_empty_input_does_not_call_codex(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        for name, mode in (("repo", "smoke"), ("model", "smoke"), ("prompt.md", "kickoff"), ("prompt.md", "resume")):
            for text in (None, "\n"):
                with self.subTest(name=name, mode=mode, text=text):
                    self.write_inputs()
                    if text is None:
                        (self.workdir / name).unlink()
                    else:
                        self.write(name, text)
                    model = "" if name == "model" else CRITIC_MODEL
                    self.assertEqual(self.run_critic(mode, reply="ok"),
                                     (1, f"exit=2 model={model} status=error:missing {name}"))
                    self.assertFalse(self.record.exists())

    def test_repo_that_is_not_a_directory_does_not_call_codex(self):
        self.write("repo", f"{self.workdir / 'no-such-repo'}\n")
        self.assertEqual(self.run_critic("smoke", reply="ok"),
                         (1, f"exit=2 model={CRITIC_MODEL} status=error:missing repo"))
        self.assertFalse(self.record.exists())

    def test_timeout_that_is_not_a_positive_number_does_not_call_codex(self):
        for text in ("soon\n", "0\n", "-5\n"):
            with self.subTest(text=text):
                self.write("timeout", text)
                self.assertEqual(self.run_critic("smoke", reply="ok"),
                                 (1, f"exit=2 model={CRITIC_MODEL} status=error:bad timeout"))
                self.assertFalse(self.record.exists())

    def test_codex_missing_from_path_is_an_error(self):
        empty_bin = self.bin.parent / "empty-bin"
        empty_bin.mkdir()
        self.write("msg.txt", STALE_REPLY)
        self.assertEqual(self.run_critic("smoke", reply="ok", path=str(empty_bin)),
                         (1, f"exit=127 model={CRITIC_MODEL} status=error:codex not found"))
        self.assertFalse(self.record.exists())
        self.assertFalse((self.workdir / "msg.txt").exists())


class SkillTextTest(unittest.TestCase):
    def test_skill_text_has_no_argument_placeholders(self):
        """Claude Code replaces $0-$9 and $ARGUMENTS in skill text when a caller passes arguments."""
        lines = SKILL.read_text(encoding="utf-8").splitlines()
        found = [f"{SKILL.name}:{number}: {line.strip()}" for number, line in enumerate(lines, 1)
                 if re.search(r"\$(\d|ARGUMENTS)", line)]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
