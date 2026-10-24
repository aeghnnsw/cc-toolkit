"""Command-line checks for the pressure-test Codex critic runner.

Each test runs the runner with a fake `codex` executable first on PATH. A
scenario file tells the fake what to print, what reply to write, how long to
sleep, and which exit code to return. The fake records its argv, working
directory, stdin, process ID, and parent process ID so the tests can check each
call. The runner starts every call in a detached supervisor, so the parent of
the fake is the supervisor, not the runner command.
"""

from __future__ import annotations

import fcntl
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
NARROW = "\nYour previous turn on this packet ran out of time.\n"
THREAD_ID = "0199a7b2-thread"
THREAD_STARTED = {"type": "thread.started", "thread_id": THREAD_ID}
STALE_REPLY = "stale reply from an earlier round"
SLEEPER = "import time; time.sleep(30)"
LIMIT_FILES = {"idle": "idle_limit", "total": "total_limit", "step": "wait_step"}
BASH_LIMITS = ("BASH_MAX_TIMEOUT_MS", "BASH_DEFAULT_TIMEOUT_MS")
STATUS_LINE = re.compile(r"exit=(-|\d+) model=(\S*) seconds=(\d+) status=(.+)")
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
# PID limit, so signals to them fail with ProcessLookupError. codex is the
# supervisor's other child, so the fake finds it even when codex was stopped
# before it ran any code. Each call appends the codex ID and its start time to a file.
SLOW_PS = """\
import os, subprocess, sys, time

if "pid=,ppid=" not in sys.argv:  # other queries, such as a process start time, pass through
    os.execv("/bin/ps", ["ps", *sys.argv[1:]])
started = time.time()
time.sleep(0.5)
table = subprocess.run(["/bin/ps", *sys.argv[1:]], capture_output=True, text=True).stdout
sys.stdout.write(table)
rows = [line.split() for line in table.splitlines()]
codex = next(int(pid) for pid, ppid in rows if int(ppid) == os.getppid() and int(pid) != os.getpid())
with open(os.environ["SLOW_PS_CALLS"], "a+", encoding="utf-8") as calls:
    calls.seek(0)
    count = len(calls.read().splitlines())
    calls.write(f"{codex} {started}\\n")
print(900000 + count, codex)
"""

# A `ps` that is slow to report a process start time. Before it waits, it writes
# the ID of its parent, the supervisor, to a file.
# Starts the runner after the test creates the go file, so that several starters
# run at the same time. Before it waits, it creates its ready file.
STARTER = """\
import os, runpy, sys, time
script, ready, go = sys.argv[1:4]
open(ready, "w").close()
while not os.path.exists(go):
    time.sleep(0.001)
sys.argv = [script, *sys.argv[4:]]
runpy.run_path(script, run_name="__main__")
"""

# Runs the runner with a pause before each write of a named file until the
# resume file exists. Before it waits, it writes its process ID to the paused file.
PAUSER = """\
import importlib.util, os, sys, time
script, name, paused, resume = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("codex_critic", script)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
write_atomic = runner.write_atomic
def paused_write(path, text):
    if path.name == name:
        with open(paused + ".tmp", "w") as handle:
            handle.write(str(os.getpid()))
        os.replace(paused + ".tmp", paused)
        while not os.path.exists(resume):
            time.sleep(0.01)
    write_atomic(path, text)
runner.write_atomic = paused_write
sys.exit(runner.main([script, *sys.argv[5:]]))
"""

SLOW_START_PS = """\
import os, sys, time

if "lstart=" in sys.argv:
    with open(os.environ["SLOW_START_PS_MARK"] + ".tmp", "w") as handle:
        handle.write(str(os.getppid()))
    os.replace(os.environ["SLOW_START_PS_MARK"] + ".tmp", os.environ["SLOW_START_PS_MARK"])
    time.sleep(5)
os.execv("/bin/ps", ["ps", *sys.argv[1:]])
"""

FAKE_CODEX = """\
import json, os, subprocess, sys, time

scenario = json.load(open(os.environ["FAKE_CODEX_SCENARIO"], encoding="utf-8"))
child = None
if scenario["child"]:  # like a Codex shell tool call: a child in its own session
    child = subprocess.Popen([sys.executable, "-c", scenario["child"]], start_new_session=True).pid
with open(scenario["record"] + ".tmp", "w", encoding="utf-8") as handle:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": sys.stdin.read(), "pid": os.getpid(),
               "ppid": os.getppid(), "child": child}, handle)
os.replace(scenario["record"] + ".tmp", scenario["record"])
with open(scenario["record"] + ".calls", "a", encoding="utf-8") as calls:  # one line for each fake codex run
    calls.write(f"{os.getpid()}\\n")
time.sleep(scenario["sleep"])
count, every, stream = scenario["heartbeat"]
for _ in range(count):  # progress output, like codex events or stderr notices during a long turn
    print('{"type": "item.started"}', file=sys.stdout if stream == "stdout" else sys.stderr, flush=True)
    time.sleep(every)
for event in scenario["events"]:
    print(event if isinstance(event, str) else json.dumps(event))
sys.stderr.write(scenario["stderr"])
if scenario["reply"] is not None:
    with open(sys.argv[sys.argv.index("-o") + 1], "w", encoding="utf-8") as handle:
        handle.write(scenario["reply"])
sys.exit(scenario["exit"])
"""


def load_factor() -> float:
    """Return the 1-minute load average per CPU, or 1 when it is lower."""
    return max(1.0, os.getloadavg()[0] / (os.cpu_count() or 1))


def scaled(seconds: float) -> float:
    """Return seconds times the load factor.

    On a loaded host, the tests and the processes that they start wait for a CPU.
    So each wait for an event, each slack above an expected time, and each fake
    call that must outlast test steps grows with the load. The limits under test
    do not change, so a run on an idle host takes the same time.
    """
    return seconds * load_factor()


def gone(pid: int, wait: float = 3.0) -> bool:
    """Return True when the process ends within the scaled wait.

    os.kill(pid, 0) also succeeds on a zombie, a process that ended but that its
    parent, or init after the parent ends, has not reaped yet; a zombie counts as ended.
    """
    deadline = time.monotonic() + scaled(wait)
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        state = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout
        if state.strip()[:1] in ("", "Z"):
            return True
        time.sleep(0.05)
    return False


def reaped(pid: int) -> bool:
    """Return True when no process, not even a zombie, has the ID."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def kill_quietly(pid: int | None) -> None:
    if pid:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def descendants(pid: int) -> list[int]:
    """Return the IDs of all processes below pid."""
    table = subprocess.run(["/bin/ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True).stdout
    children: dict[int, list[int]] = {}
    for line in table.splitlines():
        child, parent = (int(field) for field in line.split())
        children.setdefault(parent, []).append(child)
    found, stack = [], [pid]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def wait_for(condition, timeout: float = 10.0) -> bool:
    """Return True when condition() becomes true within the scaled timeout."""
    deadline = time.monotonic() + scaled(timeout)
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


class CodexCriticTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve()
        self.repo, self.workdir, self.bin = root / "repo", root / "work", root / "bin"
        for path in (self.repo, self.workdir, self.bin):
            path.mkdir()
        self.scenario, self.record = root / "scenario.json", root / "record.json"
        self.processes: list[int] = []
        self.addCleanup(self.stop_processes)
        self.install_fake("codex", FAKE_CODEX)
        self.write_inputs()

    def stop_processes(self) -> None:
        """Kill every supervisor, fake codex, and child that a test left running."""
        self.remember_call()
        for pid in self.processes:
            kill_quietly(pid)

    def remember_call(self) -> None:
        """Add the processes of the current fake codex call to the cleanup list."""
        if self.record.exists():
            call = self.call()
            self.processes += [call["ppid"], call["pid"], call["child"]]

    def install_fake(self, name: str, source: str) -> None:
        """Put an executable Python script named name first on the runner's PATH."""
        fake = self.bin / name
        fake.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
        fake.chmod(0o755)

    def write_inputs(self) -> None:
        """Write the repo, model, prompt.md, critic.txt, and narrow.txt inputs."""
        self.write("repo", f"{self.repo}\n")
        self.write("model", f"{CRITIC_MODEL}\n")
        self.write("prompt.md", PROMPT)
        self.write("critic.txt", CRITIC)
        self.write("narrow.txt", NARROW)

    def write(self, name: str, text: str) -> None:
        (self.workdir / name).write_text(text, encoding="utf-8")

    def write_limits(self, limits: dict[str, object]) -> None:
        """Write each given limit file and delete the others."""
        for key, name in LIMIT_FILES.items():
            if limits.get(key) is None:
                (self.workdir / name).unlink(missing_ok=True)
            else:
                self.write(name, f"{limits[key]}\n")

    def run_critic(self, mode: str, *, idle: object = None, total: object = None, step: object = None,
                   path: str | None = None, env: dict[str, str] | None = None, **scenario) -> tuple[int, str]:
        """Start one call with the fake codex; return the runner's exit code and its status line.

        The status line comes back without its seconds field, which self.seconds keeps.
        """
        self.prepare_call(idle=idle, total=total, step=step, **scenario)
        return self.run_runner(mode, path=path, env=env)

    def prepare_call(self, *, idle: object = None, total: object = None, step: object = None, **scenario) -> None:
        """Write the fake codex scenario and the limit files of the next call."""
        settings = {"events": [], "stderr": "", "reply": None, "exit": 0, "sleep": 0, "child": None,
                    "heartbeat": [0, 0, "stdout"]}
        settings.update(scenario, record=str(self.record))
        self.remember_call()
        self.record.unlink(missing_ok=True)
        self.scenario.write_text(json.dumps(settings), encoding="utf-8")
        self.write_limits({"idle": idle, "total": total, "step": step})

    def run_wait(self, *, step: object = None, env: dict[str, str] | None = None) -> tuple[int, str]:
        """Run the wait mode; return its exit code and its status line without the seconds field."""
        self.write_limits({"step": step})
        return self.run_runner("wait", env=env)

    def wait_until_final(self, step: float = 1) -> tuple[int, str]:
        """Run the wait mode until it reports a final status."""
        for _ in range(round(scaled(30))):
            result = self.run_wait(step=step)
            if not result[1].endswith("status=running"):
                return result
        self.fail("the call did not end")

    def runner_env(self, path: str | None, env: dict[str, str] | None) -> dict[str, str]:
        """Return the runner's environment: the fake bin first on PATH, and no Bash tool limits unless given."""
        base = {key: value for key, value in os.environ.items() if key not in BASH_LIMITS}
        base.update(env or {}, FAKE_CODEX_SCENARIO=str(self.scenario))
        base["PATH"] = path if path is not None else f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}"
        return base

    def run_runner(self, mode: str, *, path: str | None = None, env: dict[str, str] | None = None) -> tuple[int, str]:
        command = [sys.executable, str(SCRIPT), mode, str(self.workdir)]
        completed = subprocess.run(command, env=self.runner_env(path, env), capture_output=True, text=True,
                                   timeout=scaled(30))
        return completed.returncode, self.without_seconds(completed.stdout.strip())

    def without_seconds(self, line: str) -> str:
        """Check the status line form, keep its seconds in self.seconds, and return it without that field."""
        match = STATUS_LINE.fullmatch(line)
        self.assertIsNotNone(match, f"not a status line: {line!r}")
        self.seconds = int(match[3])
        return f"exit={match[1]} model={match[2]} status={match[4]}"

    def run_limited(self, ready, *, limit: str = "total", reset: tuple[Path, ...] = (),
                    **scenario) -> tuple[tuple[int, str], float]:
        """Run a kickoff that reaches a time limit; return the result and the overrun of the first ready run.

        The fake codex and its child are Python programs. On a busy machine they can
        need more than a 1-second limit to start, and then the run tests nothing. So
        while ready() is false after a run, run again with a doubled limit, up to 8
        seconds. limit names the limit under test; the other limit stays long.
        reset lists files to delete before each run.
        """
        for seconds in (1, 2, 4, 8):
            for path in reset:
                path.unlink(missing_ok=True)
            limits = {"idle": 60, "total": 60, limit: seconds}
            started = time.monotonic()
            result = self.run_critic("kickoff", sleep=seconds + 30, **limits, **scenario)
            elapsed = time.monotonic() - started
            if ready():
                return result, elapsed - seconds
        self.fail("the fake codex was not ready within an 8-second limit")

    def lock_held(self, name: str) -> bool:
        """Return True when a process holds the lock on a file in the work directory."""
        try:
            with open(self.workdir / name) as lock:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except FileNotFoundError:
            return False
        except BlockingIOError:
            return True
        return False

    def call(self) -> dict:
        """Return the argv, cwd, stdin, pid, ppid, and child pid that the fake codex recorded."""
        return json.loads(self.record.read_text(encoding="utf-8"))

    def kill_supervisor(self, signum: int = signal.SIGKILL) -> dict:
        """Signal the supervisor of the current call and wait until it is reaped; return the call record."""
        self.assertTrue(wait_for(self.record.exists), "the fake codex did not start")
        call = self.call()
        self.remember_call()
        os.kill(call["ppid"], signum)
        self.assertTrue(wait_for(lambda: reaped(call["ppid"])), "the supervisor was not reaped")
        return call

    def test_kickoff_sends_the_prompt_read_only_from_the_repo_and_saves_the_thread_id(self):
        events = [THREAD_STARTED, {"type": "turn.completed"}]
        code, line = self.run_critic("kickoff", events=events, reply="The weakest point is X.")
        self.assertEqual((code, line), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        call = self.call()
        self.assertEqual(call["argv"], [
            "exec", "--json", "--skip-git-repo-check", "--disable", "plugins", "-m", CRITIC_MODEL,
            "-c", 'model_reasoning_effort="xhigh"', "-s", "read-only", "-C", str(self.repo),
            "-o", str(self.workdir / "msg.txt"), "-",
        ])
        self.assertEqual(call["cwd"], str(self.repo))
        self.assertEqual(call["stdin"], PROMPT + CRITIC)
        self.assertEqual((self.workdir / "thread_id").read_text(encoding="utf-8"), THREAD_ID)
        self.assertEqual((self.workdir / "msg.txt").read_text(encoding="utf-8"), "The weakest point is X.")

    def test_kickoff_without_critic_text_sends_the_prompt_alone(self):
        (self.workdir / "critic.txt").unlink()
        self.assertEqual(self.run_critic("kickoff", events=[THREAD_STARTED], reply="objection"),
                         (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertEqual(self.call()["stdin"], PROMPT)

    def test_resume_passes_the_thread_id_and_the_sandbox_as_config_from_the_repo(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        code, line = self.run_critic("resume", reply="NO SUBSTANTIVE OBJECTION.")
        self.assertEqual((code, line), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        call = self.call()
        self.assertEqual(call["argv"], [
            "exec", "resume", THREAD_ID, "--json", "--skip-git-repo-check", "--disable", "plugins", "-m", CRITIC_MODEL,
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
                    "exec", "--json", "--skip-git-repo-check", "--disable", "plugins", "-m", CRITIC_MODEL,
                    "-c", 'model_reasoning_effort="low"', "-s", "read-only", "-C", str(self.repo),
                    "-o", str(self.workdir / "msg.txt"), "Reply with exactly: ok",
                ])
                self.assertEqual(call["cwd"], str(self.repo))
                self.assertEqual(call["stdin"], "")

    def test_status_line_reports_the_call_duration_in_seconds(self):
        self.assertEqual(self.run_critic("smoke", sleep=2, reply="ok"),
                         (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertGreaterEqual(self.seconds, 2)
        self.assertLess(self.seconds, 2 + scaled(6))

    def test_retry_resumes_the_saved_thread_with_the_narrow_request(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        self.assertEqual(self.run_critic("retry", reply="Q1: no substantive objection."),
                         (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        call = self.call()
        self.assertEqual(call["argv"][:3], ["exec", "resume", THREAD_ID])
        self.assertIn('sandbox_mode="read-only"', call["argv"])
        self.assertEqual(call["stdin"], PROMPT + CRITIC + NARROW)

    def test_retry_after_a_kickoff_that_stalled_before_its_thread_started_starts_a_new_thread(self):
        result, _ = self.run_limited(self.record.exists)
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        self.assertEqual((self.workdir / "thread_id").read_text(encoding="utf-8"), "")
        events = [{"type": "thread.started", "thread_id": "new-thread"}]
        self.assertEqual(self.run_critic("retry", events=events, reply="Q1: objection."),
                         (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        call = self.call()
        self.assertEqual(call["argv"][:2], ["exec", "--json"])
        self.assertIn("-C", call["argv"])
        self.assertEqual(call["stdin"], PROMPT + CRITIC + NARROW)
        self.assertEqual((self.workdir / "thread_id").read_text(encoding="utf-8"), "new-thread")

    def test_retry_as_a_kickoff_follows_the_kickoff_rules(self):
        self.assertEqual(self.run_critic("retry", events=[{"type": "turn.completed"}], reply="objection"),
                         (1, f"exit=0 model={CRITIC_MODEL} status=error:no thread id"))

    def test_a_flagged_retry_as_a_kickoff_saves_no_thread_so_its_rerun_starts_a_new_thread(self):
        flag = {"type": "error", "message": "This request has been flagged for possible cybersecurity risk."}
        self.assertEqual(self.run_critic("retry", events=[THREAD_STARTED, flag], exit=1),
                         (1, f"exit=1 model={CRITIC_MODEL} status=flagged"))
        self.assertEqual((self.workdir / "thread_id").read_text(encoding="utf-8"), "")
        self.assertEqual(self.run_critic("retry", events=[THREAD_STARTED], reply="Q1: objection."),
                         (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertEqual(self.call()["argv"][:2], ["exec", "--json"])

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
        code, line = self.run_critic("kickoff", events=[THREAD_STARTED], reply="objection",
                                     stderr=f"model rerouted: {CRITIC_MODEL} -> other\n")
        self.assertEqual((code, line), (1, f"exit=0 model={CRITIC_MODEL} status=flagged"))

    def test_flag_words_in_the_critic_reply_are_not_a_flag(self):
        words = "The plan was flagged for review; skipping it is a policy violation."
        events = [
            THREAD_STARTED,
            {"type": "item.completed", "item": {"type": "agent_message", "text": words}},
            {"type": "turn.completed"},
        ]
        self.assertEqual(self.run_critic("kickoff", events=events, reply=words),
                         (0, f"exit=0 model={CRITIC_MODEL} status=ok"))

    def test_non_zero_exit_is_an_error(self):
        self.assertEqual(self.run_critic("kickoff", events=[THREAD_STARTED], reply="partial", stderr="boom\n",
                                         exit=3),
                         (1, f"exit=3 model={CRITIC_MODEL} status=error:exit 3"))

    def test_a_call_longer_than_the_wait_step_reports_running_and_wait_gets_the_final_status(self):
        started = time.monotonic()
        code, line = self.run_critic("kickoff", step=0.5, sleep=3, events=[THREAD_STARTED], reply="late reply")
        self.assertEqual((code, line), (1, f"exit=- model={CRITIC_MODEL} status=running"))
        # The command ends at the wait step: the supervisor holds none of its output pipes.
        self.assertLess(time.monotonic() - started, 0.5 + scaled(2))
        self.assertFalse((self.workdir / "msg.txt").exists())
        self.assertEqual(self.wait_until_final(), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertGreaterEqual(self.seconds, 3)
        self.assertEqual((self.workdir / "msg.txt").read_text(encoding="utf-8"), "late reply")
        self.assertEqual((self.workdir / "thread_id").read_text(encoding="utf-8"), THREAD_ID)

    def test_wait_after_a_finished_call_prints_its_final_status_again(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        self.assertEqual(self.run_critic("resume", exit=5), (1, f"exit=5 model={CRITIC_MODEL} status=error:exit 5"))
        self.assertEqual(self.run_wait(), (1, f"exit=5 model={CRITIC_MODEL} status=error:exit 5"))

    def test_call_survives_a_kill_of_the_command_that_started_it(self):
        # The Bash tool kills a command's process group and every process below it.
        settings = {"events": [THREAD_STARTED], "stderr": "", "reply": "survived", "exit": 0, "sleep": 2,
                    "child": None, "heartbeat": [0, 0, "stdout"], "record": str(self.record)}
        self.scenario.write_text(json.dumps(settings), encoding="utf-8")
        runner = subprocess.Popen([sys.executable, str(SCRIPT), "kickoff", str(self.workdir)],
                                  env=self.runner_env(None, None), stdout=subprocess.PIPE,
                                  start_new_session=True)
        self.assertTrue(wait_for(self.record.exists), "the fake codex did not start")
        tree = descendants(runner.pid)
        os.killpg(runner.pid, signal.SIGKILL)
        for pid in tree:
            kill_quietly(pid)
        runner.communicate(timeout=scaled(10))  # the supervisor holds none of the command's output pipes
        self.assertEqual(self.wait_until_final(), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertEqual((self.workdir / "msg.txt").read_text(encoding="utf-8"), "survived")

    def test_a_second_call_while_one_runs_is_busy_and_does_not_call_codex(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        self.assertEqual(self.run_critic("resume", step=0.5, sleep=scaled(3), reply="first reply"),
                         (1, f"exit=- model={CRITIC_MODEL} status=running"))
        self.assertTrue(wait_for(self.record.exists), "the fake codex did not start")
        self.remember_call()
        for mode in ("smoke", "kickoff", "resume", "retry"):
            with self.subTest(mode=mode):
                self.assertEqual(self.run_critic(mode, reply="second reply"),
                                 (1, f"exit=2 model={CRITIC_MODEL} status=error:busy"))
                self.assertFalse(self.record.exists())
        self.assertEqual(self.wait_until_final(), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertEqual((self.workdir / "msg.txt").read_text(encoding="utf-8"), "first reply")

    def test_starts_at_the_same_time_launch_exactly_one_call(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        self.prepare_call(step=0.5, sleep=scaled(3), reply="only reply")
        go = self.workdir.parent / "go"
        starters = []
        for number in range(6):
            ready = self.workdir.parent / f"ready-{number}"
            starters.append((ready, subprocess.Popen(
                [sys.executable, "-c", STARTER, str(SCRIPT), str(ready), str(go), "resume", str(self.workdir)],
                env=self.runner_env(None, None), stdout=subprocess.PIPE, text=True)))
        self.assertTrue(wait_for(lambda: all(ready.exists() for ready, _ in starters)), "a starter did not start")
        go.touch()
        lines = sorted(self.without_seconds(starter.communicate(timeout=scaled(30))[0].strip())
                       for _, starter in starters)
        self.assertEqual(lines, [f"exit=- model={CRITIC_MODEL} status=running"]
                         + [f"exit=2 model={CRITIC_MODEL} status=error:busy"] * 5)
        self.assertEqual(self.wait_until_final(), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        calls = Path(f"{self.record}.calls").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1, "more than one codex call ran")

    def test_a_start_while_another_start_holds_the_start_lock_is_busy_and_changes_nothing(self):
        self.write("msg.txt", STALE_REPLY)
        with open(self.workdir / "start.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_critic("kickoff", reply="second reply"),
                             (1, f"exit=2 model={CRITIC_MODEL} status=error:busy"))
        self.assertFalse(self.record.exists())
        self.assertEqual((self.workdir / "msg.txt").read_text(encoding="utf-8"), STALE_REPLY)

    def test_a_kill_of_the_starting_command_keeps_the_start_lock_until_its_supervisor_wrote_call_json(self):
        self.prepare_call(step=0.5, sleep=2, events=[THREAD_STARTED], reply="first reply")
        paused, resume = self.workdir.parent / "paused", self.workdir.parent / "resume"
        starter = subprocess.Popen([sys.executable, "-c", PAUSER, str(SCRIPT), "call.json", str(paused), str(resume),
                                    "kickoff", str(self.workdir)], env=self.runner_env(None, None),
                                   stdout=subprocess.PIPE)
        self.addCleanup(kill_quietly, starter.pid)
        self.assertTrue(wait_for(paused.exists), "the supervisor did not reach its call.json write")
        supervisor = int(paused.read_text(encoding="utf-8"))
        self.processes.append(supervisor)
        self.assertNotEqual(supervisor, starter.pid)
        starter.kill()
        starter.communicate(timeout=scaled(10))
        self.assertEqual(self.run_runner("kickoff"), (1, f"exit=2 model={CRITIC_MODEL} status=error:busy"))
        resume.touch()
        self.assertEqual(self.wait_until_final(), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertEqual(self.call()["ppid"], supervisor)
        self.assertEqual((self.workdir / "msg.txt").read_text(encoding="utf-8"), "first reply")

    def test_wait_reports_runner_stopped_when_the_supervisor_ended_without_a_status(self):
        self.assertEqual(self.run_critic("kickoff", step=0.5, sleep=30, events=[THREAD_STARTED]),
                         (1, f"exit=- model={CRITIC_MODEL} status=running"))
        call = self.kill_supervisor()
        self.assertEqual(self.run_wait(), (1, f"exit=- model={CRITIC_MODEL} status=error:runner stopped"))
        self.assertTrue(gone(call["pid"]), "codex outlived the report that its call stopped")
        self.assertEqual(self.run_critic("smoke", reply="ok"), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))

    def test_a_stop_signal_to_the_supervisor_ends_its_codex_call(self):
        for signum in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=signum):
                self.assertEqual(self.run_critic("kickoff", step=0.5, sleep=30, events=[THREAD_STARTED]),
                                 (1, f"exit=- model={CRITIC_MODEL} status=running"))
                call = self.kill_supervisor(signum)
                self.assertTrue(gone(call["pid"]), "codex outlived its supervisor")
                self.assertEqual(self.run_wait(), (1, f"exit=- model={CRITIC_MODEL} status=error:runner stopped"))

    def test_codex_does_not_start_when_its_supervisor_dies_before_recording_it(self):
        self.install_fake("ps", SLOW_START_PS)
        mark = self.workdir.parent / "supervisor"
        self.assertEqual(self.run_critic("kickoff", step=0.5, events=[THREAD_STARTED], reply="unrecorded",
                                         env={"SLOW_START_PS_MARK": str(mark)}),
                         (1, f"exit=- model={CRITIC_MODEL} status=running"))
        self.assertTrue(wait_for(mark.exists), "the supervisor did not look up the codex start time")
        supervisor = int(mark.read_text(encoding="utf-8"))
        self.processes.append(supervisor)
        os.kill(supervisor, signal.SIGKILL)
        self.assertTrue(wait_for(lambda: reaped(supervisor)), "the supervisor was not reaped")
        time.sleep(1.5)
        self.remember_call()
        self.assertFalse(self.record.exists(), "codex ran before its supervisor recorded it")
        self.assertFalse((self.workdir / "msg.txt").exists())

    def test_codex_does_not_start_when_call_json_names_another_supervisor_before_it_is_recorded(self):
        self.install_fake("ps", SLOW_START_PS)
        mark = self.workdir.parent / "supervisor"
        self.assertEqual(self.run_critic("kickoff", step=0.5, events=[THREAD_STARTED], reply="unrecorded",
                                         env={"SLOW_START_PS_MARK": str(mark)}),
                         (1, f"exit=- model={CRITIC_MODEL} status=running"))
        self.assertTrue(wait_for(mark.exists), "the supervisor did not look up the codex start time")
        supervisor = int(mark.read_text(encoding="utf-8"))
        self.processes.append(supervisor)
        other = {"pid": os.getpid(), "model": CRITIC_MODEL, "started": time.time(), "total": 1800}
        self.write("call.json", json.dumps(other))
        self.assertTrue(wait_for(lambda: reaped(supervisor), timeout=15), "the supervisor did not end")
        self.remember_call()
        self.assertFalse(self.record.exists(), "codex ran although call.json named another supervisor")
        self.assertEqual(json.loads((self.workdir / "call.json").read_text(encoding="utf-8")), other)
        self.assertFalse((self.workdir / "status.json").exists())

    def test_a_new_call_ends_the_codex_process_of_a_call_whose_supervisor_was_killed(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        self.assertEqual(self.run_critic("resume", step=0.5, sleep=3, reply="old reply"),
                         (1, f"exit=- model={CRITIC_MODEL} status=running"))
        old = self.kill_supervisor()
        self.assertEqual(self.run_critic("resume", reply="new reply"), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
        self.assertTrue(gone(old["pid"]), "the old codex call still runs")
        time.sleep(3.5)  # the old call would write its reply now
        self.assertEqual((self.workdir / "msg.txt").read_text(encoding="utf-8"), "new reply")

    def test_a_call_past_its_total_limit_and_margin_is_stopped_and_its_supervisor_killed(self):
        # A stuck supervisor still holds its lock long after its total limit.
        holds_lock = ("import fcntl, sys, time; lock = open(sys.argv[1], 'a'); fcntl.flock(lock, fcntl.LOCK_EX); "
                      "time.sleep(60)")
        supervisor = subprocess.Popen([sys.executable, "-c", holds_lock, str(self.workdir / "call.lock")])
        self.addCleanup(lambda: (kill_quietly(supervisor.pid), supervisor.wait()))
        self.assertTrue(wait_for(lambda: self.lock_held("call.lock")), "the stand-in supervisor did not lock")
        call = {"pid": supervisor.pid, "model": CRITIC_MODEL, "started": time.time() - 2000, "total": 1800}
        self.write("call.json", json.dumps(call))
        self.assertEqual(self.run_wait(), (1, f"exit=- model={CRITIC_MODEL} status=error:runner stopped"))
        self.assertTrue(gone(supervisor.pid), "the stuck supervisor still runs")
        self.assertEqual(self.run_critic("smoke", reply="ok"), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))

    def test_a_supervisor_past_the_margin_cannot_write_its_status_into_the_next_call(self):
        self.prepare_call(step=0.5, events=[THREAD_STARTED], reply="old reply")
        paused, resume = self.workdir.parent / "paused", self.workdir.parent / "resume"
        starter = subprocess.Popen([sys.executable, "-c", PAUSER, str(SCRIPT), "status.json", str(paused),
                                    str(resume), "kickoff", str(self.workdir)], env=self.runner_env(None, None),
                                   stdout=subprocess.PIPE, text=True)
        self.addCleanup(kill_quietly, starter.pid)
        self.assertEqual(self.without_seconds(starter.communicate(timeout=scaled(30))[0].strip()),
                         f"exit=- model={CRITIC_MODEL} status=running")
        self.assertTrue(wait_for(paused.exists), "the supervisor did not reach its status write")
        supervisor = int(paused.read_text(encoding="utf-8"))
        self.processes.append(supervisor)
        old = json.loads((self.workdir / "call.json").read_text(encoding="utf-8"))
        self.write("call.json", json.dumps(dict(old, started=time.time() - 2000)))  # past the total limit and margin
        self.assertEqual(self.run_critic("kickoff", step=0.5, sleep=scaled(5), exit=5, events=[THREAD_STARTED]),
                         (1, f"exit=- model={CRITIC_MODEL} status=running"))
        self.assertTrue(gone(supervisor), "the supervisor past the margin still runs")
        resume.touch()
        time.sleep(0.5)
        self.assertEqual(self.run_wait(step=0.5), (1, f"exit=- model={CRITIC_MODEL} status=running"))
        self.assertEqual(self.wait_until_final(), (1, f"exit=5 model={CRITIC_MODEL} status=error:exit 5"))

    def test_a_supervisor_that_ended_but_was_not_reaped_counts_as_stopped(self):
        # Under a PID 1 that does not reap orphans, an ended supervisor stays a zombie.
        codex = subprocess.Popen([sys.executable, "-c", SLEEPER], start_new_session=True)
        self.addCleanup(lambda: (kill_quietly(codex.pid), codex.wait()))
        codex_start = subprocess.run(["/bin/ps", "-o", "lstart=", "-p", str(codex.pid)], capture_output=True,
                                     text=True).stdout.strip()
        holds_lock = "import fcntl, sys; fcntl.flock(open(sys.argv[1], 'a'), fcntl.LOCK_EX)"
        supervisor = subprocess.Popen([sys.executable, "-c", holds_lock, str(self.workdir / "call.lock")])
        self.addCleanup(supervisor.wait)
        self.assertTrue(wait_for(lambda: subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(supervisor.pid)],
                                                        capture_output=True, text=True).stdout.startswith("Z")),
                        "the stand-in supervisor did not become a zombie")
        call = {"pid": supervisor.pid, "model": CRITIC_MODEL, "started": time.time(), "total": 1800,
                "codex": codex.pid, "codex_start": codex_start}
        self.write("call.json", json.dumps(call))
        self.assertEqual(self.run_wait(step=5), (1, f"exit=- model={CRITIC_MODEL} status=error:runner stopped"))
        self.assertTrue(gone(codex.pid), "the codex process of the ended supervisor still runs")
        self.assertEqual(self.run_critic("smoke", reply="ok"), (0, f"exit=0 model={CRITIC_MODEL} status=ok"))

    def test_wait_without_a_call_is_an_error(self):
        self.assertEqual(self.run_wait(), (1, f"exit=2 model={CRITIC_MODEL} status=error:no call"))

    def test_wait_step_fits_inside_a_lower_bash_tool_limit(self):
        # Both steps are the 5-second floor: 32 s - 30 s = 2 s, and 1 s - 30 s is below 0.
        for limit, low, slack in (("32000", 1.5, 1), ("1000", 5, 5)):
            with self.subTest(limit=limit):
                env = dict.fromkeys(BASH_LIMITS, limit)
                started = time.monotonic()
                self.assertEqual(self.run_critic("kickoff", env=env, sleep=30),
                                 (1, f"exit=- model={CRITIC_MODEL} status=running"))
                elapsed = time.monotonic() - started
                kill_quietly(self.kill_supervisor()["pid"])  # before the checks, so the next subtest is not busy
                self.assertGreaterEqual(elapsed, low)
                self.assertLess(elapsed, 5 + scaled(slack))

    def test_timeout_kills_the_call_and_reports_exit_124(self):
        result, overrun = self.run_limited(self.record.exists, reply="late reply")
        self.assertLess(overrun, scaled(3))
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        with self.assertRaises(ProcessLookupError):  # the runner killed the call; it did not leave it running
            os.kill(self.call()["pid"], 0)

    def test_call_with_no_output_for_the_idle_limit_is_stopped_with_error_idle(self):
        result, overrun = self.run_limited(self.record.exists, limit="idle")
        self.assertLess(overrun, scaled(3))
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:idle"))
        with self.assertRaises(ProcessLookupError):
            os.kill(self.call()["pid"], 0)

    def test_output_on_stdout_or_stderr_keeps_a_call_inside_the_idle_limit(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                # The idle limit also covers the start of codex. One factor for the whole call keeps the
                # heartbeats about twice as long as the idle limit.
                factor = load_factor()
                result = self.run_critic("kickoff", idle=2.5 * factor, total=60 * factor,
                                         heartbeat=[round(12 * factor), 0.4, stream], events=[THREAD_STARTED],
                                         reply="steady")
                self.assertEqual(result, (0, f"exit=0 model={CRITIC_MODEL} status=ok"))
                self.assertGreaterEqual(self.seconds, 4 * factor)

    def test_call_that_keeps_printing_past_the_total_limit_is_stopped_with_error_timeout(self):
        result = self.run_critic("kickoff", idle=60, total=2, heartbeat=[100, 0.2, "stdout"])
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        self.assertLess(self.seconds, 2 + scaled(4))

    def test_timeout_also_kills_children_in_their_own_session(self):
        result, _ = self.run_limited(self.record.exists, child=SLEEPER)
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        child = self.call()["child"]
        self.addCleanup(kill_quietly, child)
        self.assertTrue(gone(child), "a child in its own session survived the timeout")

    def test_timeout_kills_grandchildren_that_a_detached_child_keeps_starting(self):
        forks = self.workdir.parent / "grandchildren.txt"

        def ready():  # the child started at least one grandchild before the runner stopped it
            return self.record.exists() and forks.exists() and bool(forks.read_text(encoding="utf-8").split())

        result, _ = self.run_limited(ready, reset=(forks,), child=FORKER.format(forks=str(forks)))
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
        calls = self.workdir.parent / "ps_calls"
        result = self.run_critic("kickoff", total=1, sleep=30, env={"SLOW_PS_CALLS": str(calls)})
        ended = time.time()
        self.assertEqual(result, (1, f"exit=124 model={CRITIC_MODEL} status=error:timeout"))
        scans = [line.split() for line in calls.read_text(encoding="utf-8").splitlines()] if calls.exists() else []
        self.assertGreaterEqual(len(scans), 2, "the scans stopped before the deadline")
        # The first scan starts after the timeout, so slow starts of the runner or codex do not count.
        self.assertLess(ended - float(scans[0][1]), 5 + scaled(2.5), "cleanup ran past its 5-second deadline")
        self.assertTrue(gone(int(scans[0][0]), wait=1), "codex survived the timeout")

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
        self.assertEqual(self.seconds, 0)
        self.assertFalse(self.record.exists())
        self.assertFalse((self.workdir / "msg.txt").exists())

    def test_missing_or_empty_input_does_not_call_codex(self):
        self.write("thread_id", f"{THREAD_ID}\n")
        cases = (("repo", "smoke"), ("model", "smoke"), ("prompt.md", "kickoff"), ("prompt.md", "resume"),
                 ("prompt.md", "retry"), ("narrow.txt", "retry"))
        for name, mode in cases:
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
                    self.assertEqual(self.run_wait(), (1, f"exit=2 model={model} status=error:no call"))

    def test_repo_that_is_not_a_directory_does_not_call_codex(self):
        self.write("repo", f"{self.workdir / 'no-such-repo'}\n")
        self.assertEqual(self.run_critic("smoke", reply="ok"),
                         (1, f"exit=2 model={CRITIC_MODEL} status=error:missing repo"))
        self.assertFalse(self.record.exists())

    def test_limit_that_is_not_a_positive_number_does_not_call_codex(self):
        for key in LIMIT_FILES:
            for text in ("soon", "0", "-5"):
                with self.subTest(limit=LIMIT_FILES[key], text=text):
                    self.assertEqual(self.run_critic("smoke", reply="ok", **{key: text}),
                                     (1, f"exit=2 model={CRITIC_MODEL} status=error:bad limit"))
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
