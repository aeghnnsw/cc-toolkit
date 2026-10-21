import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "zsh_traps.py"
ZSH = shutil.which("zsh")


def load_hook_module():
    spec = importlib.util.spec_from_file_location("zsh_traps", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


zsh_traps = load_hook_module()


# Each command has an unquoted word that zsh reads as `=name`; the value is
# the word that the warning names.
EQUALS_TRAPS = {
    "echo =====": "=====",
    "echo ok; echo ===": "===",
    '[ "a" == "a" ]': "==",
    "test a ==b": "==b",
    "SEP=====; echo $SEP": "====",
    "export SEP=====": "====",
    "cat <<< ===": "===",
    "cat <<'EOF'\nbody\nEOF\necho ====": "====",
    "if [[ -n x ]]; then echo ====; fi": "====",
    "n=$(echo ====)": "====",
    'echo "$(echo ====)"': "====",
}

# Commands that zsh runs without an `=name` expansion.
EQUALS_SAFE = [
    "echo '=====' \"=====\" \\=====",
    "echo = a==b --opt=v foo=====bar",
    "SEP==; echo $SEP",
    "[ a = a ]",
    'a=x; [[ "$a" == x && $a == x ]] && echo same',
    "if [[ x == x ]]; then echo same; fi",
    "(( 1 == 1 )) && echo $(( 2 == 2 ))",
    "for (( i = 0; i == 0; i++ )); do echo $i; done",
    "cat <<'EOF'\n=====\nEOF",
    "cat <<EOF\n=====\nEOF",
    "echo hi # =====",
    "cat =(echo a) <(echo b)",
    "awk '$1 == 1' /dev/null",
]

# Each command reads an unquoted variable that zsh does not split; the value
# is the word that the warning names.
SPLIT_TRAPS = {
    'PY="uv run python"; $PY -V': "$PY",
    "PY='uv run python'; ${PY} -V": "${PY}",
    'ARGS="-v --fast"; pytest $ARGS': "$ARGS",
    'PY="uv run python"; out=$($PY -V)': "$PY",
    'f() { local CMD="ls -l"; $CMD; }; f': "$CMD",
    "pr=$(gh pr list --json number); set -- $pr": "$pr",
    'files=$(git ls-files); for f in $files; do echo "$f"; done': "$files",
    'for line in "a b"; do set -- $line; done': "$line",
}

SPLIT_SAFE = [
    'PY="uv run python"; echo "$PY"',
    "sha=$(git rev-parse HEAD); git show $sha",
    'for f in $(git ls-files); do echo "$f"; done',
    "files=(a b c); for f in $files; do echo $f; done",
    "a=$(echo 1); b=$(echo 2); for n in $a $b; do echo $n; done",
    'set -euo pipefail; set -- "$a" $b',
    "pr=$(gh pr list); set -- ${=pr}",
    'cmd="ls -l"; eval $cmd',
    'py() { uv run python "$@"; }; py -V',
    "bash -c 'PY=\"uv run python\"; $PY -V'",
    'X="a b"; [[ $X == "a b" ]]',
    "cat <<'EOF'\nPY=\"uv run python\"; $PY -V\nEOF",
]


def run_hook(command, shell="/bin/zsh"):
    env = os.environ.copy()
    env["SHELL"] = shell
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
        timeout=30,
    )


class ZshTrapWarningTests(unittest.TestCase):
    def test_warns_about_an_unquoted_word_that_starts_with_equals(self):
        for command, word in EQUALS_TRAPS.items():
            with self.subTest(command=command):
                warnings = zsh_traps.zsh_trap_warnings(command)
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn(f"`{word}` starts with `=`", warnings[0])
                self.assertIn(f"`'{word}'`", warnings[0])

    def test_warns_about_an_unsplit_variable(self):
        for command, word in SPLIT_TRAPS.items():
            with self.subTest(command=command):
                warnings = zsh_traps.zsh_trap_warnings(command)
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn(f"variable `{word}`", warnings[0])
                self.assertIn("define a function", warnings[0])
                self.assertIn("with `bash`", warnings[0])

    def test_gives_no_warning_for_safe_commands(self):
        for command in EQUALS_SAFE + SPLIT_SAFE:
            with self.subTest(command=command):
                self.assertEqual(zsh_traps.zsh_trap_warnings(command), [])

    @unittest.skipUnless(ZSH, "zsh is not installed")
    def test_equals_cases_match_zsh(self):
        cases = [(command, True) for command in EQUALS_TRAPS]
        cases += [(command, False) for command in EQUALS_SAFE]
        with tempfile.TemporaryDirectory() as temp_dir:
            for command, fails in cases:
                with self.subTest(command=command):
                    result = subprocess.run(
                        [ZSH, "-f", "-c", command],
                        text=True,
                        capture_output=True,
                        cwd=temp_dir,
                        check=False,
                        timeout=30,
                    )
                    self.assertEqual(
                        " not found" in result.stderr, fails, result.stderr
                    )

    def test_hook_gives_the_agent_the_warning_under_zsh(self):
        result = run_hook("echo =====")

        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        context = response["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(response["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertIn("Quote the word", context)
        self.assertEqual(response["systemMessage"], context)

    def test_hook_is_silent_for_a_safe_command_or_another_shell(self):
        for command, shell in (("echo '====='", "/bin/zsh"), ("echo =====", "/bin/bash")):
            with self.subTest(command=command, shell=shell):
                result = run_hook(command, shell=shell)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
