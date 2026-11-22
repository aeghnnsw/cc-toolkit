"""Run the critic-model shell blocks of the pressure-test copies in bash and zsh.

Each check runs the Setup block of a copy, then its Critic model block, its
Flags block, or both, each in a new shell as the agent runs them, and reads the critic model
file in the work directory. The blocks come from SKILL.md, so the checks cover the text
that an agent runs. The expected models come from allowed-models.json. The Antigravity
main agent can run a GPT-family model, so its copy must stop before setup (issue #433).

The Codex copy runs its Claude critic through a critic() shell function in SKILL.md. A
check runs its Setup, kickoff, and later-round blocks with a fake `claude` that records its
argv, working directory, and environment. Text checks make every stop name one ending
condition and keep the same ending conditions in every copy (issue #460).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_MODELS = json.loads((PLUGIN_ROOT.parent / "allowed-models.json").read_text(encoding="utf-8"))
# Each copy calls a critic from a model family other than the main agent's.
COPIES = {
    "claude-code": (PLUGIN_ROOT / "skills" / "pressure-test" / "SKILL.md", "gpt"),
    "codex": (PLUGIN_ROOT / "codex-skills" / "pressure-test" / "SKILL.md", "claude"),
    "antigravity": (PLUGIN_ROOT / "antigravity-skills" / "pressure-test" / "SKILL.md", "gpt"),
}
NO_CRITIC = "no cross-family critic"  # the ending condition of a GPT-family Antigravity main agent
SHELLS = {"bash": ["bash", "-c"], "zsh": ["zsh", "-f", "-c"]}  # -f: no user startup files
CASES = [(copy, shell, ALLOWED_MODELS[family]) for copy, (_, family) in COPIES.items() for shell in SHELLS]
BASH_FENCE = re.compile(r"^[ \t]*```bash[ \t]*\n(.*?)^[ \t]*```", re.MULTILINE | re.DOTALL)
WORKDIR_LINE = re.compile(r"^workdir: (.+)$", re.MULTILINE)
# A stop instruction: "— stop.", "**STOP** and report", or "stop and report".
STOP = re.compile(r"—\s*stop\.|\bstop\b\** and report\b", re.IGNORECASE)
NAMED_ENDING = re.compile(r'ending condition is\s+"([^"]+)"')
ITEM_START = re.compile(r"^\s*(?:[-*]|\d+\.)\s")
LOOP_ENDINGS = {"converged", "round cap"}  # the review loop ends with these; no stop instruction names them
# A fake Claude CLI: it appends its argv, working directory, environment, and stdin to the
# file in FAKE_CLAUDE_RECORD, and prints the stream-json events of a reply from the model in --model.
FAKE_CLAUDE = """\
import json, os, sys
argv = sys.argv[1:]
record = os.environ["FAKE_CLAUDE_RECORD"]
with open(record, "a", encoding="utf-8") as calls:
    calls.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "env": dict(os.environ),
                            "stdin": sys.stdin.read()}) + "\\n")
with open(record, encoding="utf-8") as calls:
    reply = f"objection {len(calls.readlines())}"
message = {"model": argv[argv.index("--model") + 1], "content": [{"type": "text", "text": reply}],
           "stop_reason": "end_turn"}
print(json.dumps({"type": "assistant", "message": message}))
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": reply,
                  "stop_reason": "end_turn", "safety_stops": 0}))
"""


def section(text: str, title: str) -> str:
    """Return the text under the level-2 heading that starts with title, ignoring case, or ""."""
    match = re.search(rf"^## {re.escape(title)}\b.*$", text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    end = re.compile(r"^## ", re.MULTILINE).search(text, match.end())
    return text[match.end():end.start() if end else len(text)]


def first_block(text: str, title: str) -> str:
    """Return the first bash block under a level-2 heading, or "" when there is none."""
    match = BASH_FENCE.search(section(text, title))
    return match.group(1) if match else ""


def items(text: str) -> list[str]:
    """Return each paragraph, list item, and heading outside code fences as one line of text."""
    found, current, fenced = [], [], False
    for line in text.splitlines():
        fence = line.lstrip().startswith("```")
        if fence or not line.strip() or ITEM_START.match(line) or line.startswith("#"):
            if current:
                found.append(" ".join(current))
            current = []
        if fence:
            fenced = not fenced
        elif not fenced and line.strip():
            current.append(line.strip())
    if current:
        found.append(" ".join(current))
    return found


def ending_conditions(text: str) -> list[str]:
    """Return the ending conditions in the "ending condition:" item of the conclusion section."""
    prefix = "- ending condition:"
    conclusion = section(text, "Step 3") or section(text, "Conclusion")
    entry = next((item for item in items(conclusion) if item.startswith(prefix)), prefix)
    return [name for name in re.split(r",\s*(?:or\s+)?|\s+or\s+", entry[len(prefix):].strip()) if name]


class CriticModelBlockTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temp = directory.name
        # Setup creates the work directory under TMPDIR, so the cleanup removes it.
        self.env = dict(os.environ, TMPDIR=self.temp, CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT))

    def require_shell(self, shell: str) -> None:
        """Skip the current subtest when the shell is not installed."""
        if shutil.which(shell) is None:
            self.skipTest(f"{shell} is not installed")

    def run_block(self, shell: str, block: str, workdir: str = "",
                  cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        """Run one block in a new shell, from cwd or the temporary directory, and return the result.

        Fail on a non-zero exit.
        """
        result = subprocess.run([*SHELLS[shell], block.replace("<workdir>", workdir)], cwd=cwd or self.temp,
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def run_named_block(self, copy: str, text: str, shell: str, title: str, workdir: Path) -> None:
        """Run the first bash block under a heading of the copy; fail when the heading has none."""
        block = first_block(text, title)
        self.assertTrue(block, f"{copy}: no bash block under {title}")
        self.run_block(shell, block, str(workdir))

    def start_pressure_test(self, copy: str, shell: str, start: str) -> tuple[str, Path]:
        """Run the Setup block of a copy, and the Critic model block when start is "fallback".

        Return the SKILL.md text and the work directory.
        """
        path = COPIES[copy][0]
        text = path.read_text(encoding="utf-8")
        block = first_block(text, "Setup").replace("<skill-dir>", str(path.parent))
        self.assertTrue(block, f"{copy}: no bash block under Setup")
        result = self.run_block(shell, block)
        match = WORKDIR_LINE.search(result.stdout)
        self.assertIsNotNone(match, f"{copy}: Setup printed no workdir line; stderr:\n{result.stderr}")
        self.assertNotIn("runner not found", result.stdout, f"{copy}: Setup found no runner")
        workdir = Path(match.group(1))
        self.assertEqual(workdir.parent, Path(self.temp), f"{copy}: Setup ignored TMPDIR")
        if start == "fallback":
            self.run_named_block(copy, text, shell, "Critic model", workdir)
        return text, workdir

    def critic_model(self, workdir: Path) -> str:
        """Return the model in the critic model file of a work directory."""
        return (workdir / "model").read_text(encoding="utf-8").strip()

    def test_pressure_test_starts_on_the_primary_or_the_chosen_fallback_model(self):
        for copy, shell, models in CASES:
            for start in ("primary", "fallback"):
                with self.subTest(copy=copy, shell=shell, start=start):
                    self.require_shell(shell)
                    _, workdir = self.start_pressure_test(copy, shell, start)
                    self.assertEqual(self.critic_model(workdir), models[start])

    def test_flag_switch_moves_to_the_other_allowed_model(self):
        for copy, shell, models in CASES:
            for start, other in (("primary", "fallback"), ("fallback", "primary")):
                with self.subTest(copy=copy, shell=shell, start=start):
                    self.require_shell(shell)
                    text, workdir = self.start_pressure_test(copy, shell, start)
                    self.run_named_block(copy, text, shell, "Flags", workdir)
                    self.assertEqual(self.critic_model(workdir), models[other])

    def test_codex_critic_runs_claude_read_only_from_the_repo_on_the_current_model(self):
        root = Path(self.temp)
        fake_bin, elsewhere, record = root / "bin", root / "elsewhere", root / "claude-calls.jsonl"
        fake_bin.mkdir()
        elsewhere.mkdir()  # the blocks run from here, so only critic() can move the call to $REPO
        (fake_bin / "claude").write_text(f"#!{sys.executable}\n{FAKE_CLAUDE}", encoding="utf-8")
        (fake_bin / "claude").chmod(0o755)
        self.env.pop("CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK", None)
        self.env.update(PATH=f"{fake_bin}{os.pathsep}{self.env.get('PATH', '')}", FAKE_CLAUDE_RECORD=str(record))
        model = ALLOWED_MODELS["claude"]["fallback"]  # from $DIR/model; $PRIMARY_MODEL names the other model
        for shell in SHELLS:
            with self.subTest(shell=shell):
                self.require_shell(shell)
                record.unlink(missing_ok=True)
                text, workdir = self.start_pressure_test("codex", shell, "fallback")
                repo = re.search(r'^REPO="(.*)"$', (workdir / "env.sh").read_text(encoding="utf-8"), re.MULTILINE)
                self.assertIsNotNone(repo, "Setup wrote no REPO to env.sh")
                kickoff, later = BASH_FENCE.findall(section(text, "Calling The Critic"))[:2]
                outputs = [self.run_block(shell, block, str(workdir), cwd=str(elsewhere)).stdout
                           for block in (kickoff, later)]
                session = (workdir / "session_id").read_text(encoding="utf-8").strip()
                calls = [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(calls), 2)
                for number, (call, flags, output) in enumerate(
                        zip(calls, (["--session-id", session], ["--resume", session]), outputs), 1):
                    self.assertEqual(call["argv"], [
                        "-p", "--model", model, "--effort", "xhigh", *flags, "--output-format", "stream-json",
                        "--verbose", "--tools", "Read,Grep,Glob", "--permission-mode", "dontAsk",
                        "--strict-mcp-config", "--disable-slash-commands", "--add-dir", str(workdir),
                    ])
                    self.assertEqual(os.path.realpath(call["cwd"]), os.path.realpath(repo.group(1)))
                    self.assertNotEqual(os.path.realpath(call["cwd"]), os.path.realpath(elsewhere))
                    self.assertEqual(call["env"].get("CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK"), "1")
                    self.assertTrue(call["stdin"].endswith((workdir / "critic.txt").read_text(encoding="utf-8")))
                    self.assertRegex(output,
                                     rf"\Aexit=0 model={re.escape(model)} seconds=\d+\nok\nobjection {number}\n?\Z")
                # replies.md keeps both replies after the later round replaced msg.txt.
                self.assertRegex((workdir / "replies.md").read_text(encoding="utf-8"), "".join(
                    rf"## critic call\n\nexit=0 model={re.escape(model)} seconds=\d+\nok\n\nobjection {number}\n\n"
                    for number in (1, 2)) + r"\Z")


class EndingConditionTests(unittest.TestCase):
    def test_every_stop_names_one_ending_condition_from_the_list_that_all_copies_share(self):
        """Every stop needs a conclusion with an ending condition, and the copies list the same ones (#460)."""
        expected = ending_conditions(COPIES["claude-code"][0].read_text(encoding="utf-8"))
        self.assertIn("cut short", expected)
        for copy, (path, _) in COPIES.items():
            with self.subTest(copy=copy):
                text = path.read_text(encoding="utf-8")
                found = ending_conditions(text)
                extra = {NO_CRITIC} if copy == "antigravity" else set()  # the only host-specific ending
                self.assertEqual(len(found), len(set(found)), f"{copy}: an ending condition is listed twice")
                self.assertEqual(set(found), set(expected) | extra)
                listed = set(found)
                stops = [item for item in items(text) if STOP.search(item)]
                self.assertTrue(stops, f"{copy}: no stop instruction found")
                for item in stops:
                    named = set(NAMED_ENDING.findall(item))
                    self.assertEqual(len(named), 1, f"{copy}: a stop names {sorted(named)} ending conditions: {item}")
                    self.assertLessEqual(named, listed, f"{copy}: a stop names an unlisted ending condition: {item}")
                named_anywhere = set(NAMED_ENDING.findall(" ".join(items(text))))
                self.assertEqual(named_anywhere, listed - LOOP_ENDINGS,
                                 f"{copy}: each listed ending condition outside the loop needs a rule that names it")


class CrossFamilyStopTests(unittest.TestCase):
    def test_antigravity_copy_stops_on_a_gpt_family_main_agent_before_setup(self):
        text = COPIES["antigravity"][0].read_text(encoding="utf-8")
        check = section(text, "Cross-family check")
        self.assertIn("GPT-family", check)
        self.assertIn(f'"{NO_CRITIC}"', check)
        self.assertLess(text.index("## Cross-family check"), text.index("## Setup"))
        self.assertIn(NO_CRITIC, section(text, "Stop conditions").lower())
        self.assertIn(NO_CRITIC, section(text, "Step 3").lower())


if __name__ == "__main__":
    unittest.main()
