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


# Each command has an unquoted word `=name` that names no command, so zsh
# stops the command line; the value is the word that the denial names.
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

# zsh replaces `=sh` with the path of `sh`; the hook warns but allows it.
EQUALS_FOUND = "echo =sh"

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

# In a directory that holds only `a.txt` and `sub/b.md`, each command has an
# unquoted glob that matches no file; the value is the word that the warning
# names.
GLOB_TRAPS = {
    "ls *.md": "*.md",
    "grep -r --include=*.md x .": "--include=*.md",
    "echo ok; grep -l x */config.json": "*/config.json",
    "curl -s https://example.test/a?b=c": "https://example.test/a?b=c",
    "echo [WIP]": "[WIP]",
    "for f in *.md; do echo $f; done": "*.md",
    "n=$(ls *.md)": "*.md",
    "cd sub && grep -r --include=*.md x .": "--include=*.md",
}

# Commands in the same directory whose globs match a file or are not globs.
GLOB_SAFE = [
    "ls *.txt a?txt [ab].txt sub/*.md",
    "echo '*.md' \"*.md\" \\*.md",
    "grep -r --include='*.md' x .",
    "noglob echo *.md",
    "case a.md in *.md) echo md;; *) echo other;; esac",
    'X=*.md; echo "$X"',
    "[[ a.md == *.md ]] && echo md",
    "[ -f a.txt ]",
    "cd sub && ls *.md",
]


def glob_directory(temp_dir):
    """Fill `temp_dir` with `a.txt` and `sub/b.md`, and return its path."""
    Path(temp_dir, "a.txt").touch()
    Path(temp_dir, "sub").mkdir()
    Path(temp_dir, "sub", "b.md").touch()
    return temp_dir


def run_zsh(command, cwd):
    return subprocess.run(
        [ZSH, "-f", "-c", command],
        text=True,
        capture_output=True,
        cwd=cwd,
        check=False,
        timeout=30,
    )


def run_hook(command, shell="/bin/zsh", cwd=None):
    env = os.environ.copy()
    env["SHELL"] = shell
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    if cwd:
        payload["cwd"] = cwd
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
        timeout=30,
    )


class ZshTrapTests(unittest.TestCase):
    def test_denies_an_equals_word_that_names_no_command(self):
        for command, word in EQUALS_TRAPS.items():
            with self.subTest(command=command):
                traps = zsh_traps.zsh_traps(command)
                self.assertEqual([trap.stops_line for trap in traps], [True], traps)
                self.assertIn(f"`{word}` starts with `=`", traps[0].message)
                self.assertIn(f"`'{word}'`", traps[0].message)

    def test_warns_about_an_equals_word_that_names_a_command(self):
        traps = zsh_traps.zsh_traps(EQUALS_FOUND)

        self.assertEqual([trap.stops_line for trap in traps], [False], traps)
        self.assertIn("`=sh` starts with `=`", traps[0].message)

    def test_warns_about_an_unsplit_variable(self):
        for command, word in SPLIT_TRAPS.items():
            with self.subTest(command=command):
                traps = zsh_traps.zsh_traps(command)
                self.assertEqual([trap.stops_line for trap in traps], [False], traps)
                self.assertIn(f"variable `{word}`", traps[0].message)
                self.assertIn("define a function", traps[0].message)
                self.assertIn("with `bash`", traps[0].message)

    def test_warns_about_a_glob_that_matches_no_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = glob_directory(temp_dir)
            for command, word in GLOB_TRAPS.items():
                with self.subTest(command=command):
                    traps = zsh_traps.zsh_traps(command, directory)
                    self.assertEqual([trap.stops_line for trap in traps], [False], traps)
                    self.assertIn(f"glob `{word}` matches no file", traps[0].message)

    def test_gives_no_finding_for_safe_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = glob_directory(temp_dir)
            for command in EQUALS_SAFE + SPLIT_SAFE + GLOB_SAFE:
                with self.subTest(command=command):
                    self.assertEqual(zsh_traps.zsh_traps(command, directory), [])

    def test_checks_only_option_globs_without_a_directory(self):
        self.assertEqual(zsh_traps.zsh_traps("ls *.md"), [])
        self.assertEqual(len(zsh_traps.zsh_traps("grep -r --include=*.md x .")), 1)

    @unittest.skipUnless(ZSH, "zsh is not installed")
    def test_equals_cases_match_zsh(self):
        cases = [(command, True) for command in EQUALS_TRAPS]
        cases += [(command, False) for command in EQUALS_SAFE + [EQUALS_FOUND]]
        with tempfile.TemporaryDirectory() as temp_dir:
            for command, fails in cases:
                with self.subTest(command=command):
                    result = run_zsh(command, temp_dir)
                    self.assertEqual(
                        " not found" in result.stderr, fails, result.stderr
                    )

    @unittest.skipUnless(ZSH, "zsh is not installed")
    def test_glob_cases_match_zsh(self):
        cases = [(command, True) for command in GLOB_TRAPS]
        cases += [(command, False) for command in GLOB_SAFE]
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = glob_directory(temp_dir)
            for command, fails in cases:
                with self.subTest(command=command):
                    result = run_zsh(command, directory)
                    self.assertEqual(
                        "no matches found" in result.stderr, fails, result.stderr
                    )

    def test_hook_denies_a_command_that_zsh_would_stop(self):
        result = run_hook("echo =====")

        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        output = response["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("Quote the word", output["permissionDecisionReason"])
        self.assertNotIn("additionalContext", output)
        self.assertEqual(response["systemMessage"], output["permissionDecisionReason"])

    def test_hook_gives_the_agent_a_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for command, text in ((EQUALS_FOUND, "Quote the word"), ("ls *.md", "matches no file")):
                with self.subTest(command=command):
                    result = run_hook(command, cwd=temp_dir)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    response = json.loads(result.stdout)
                    output = response["hookSpecificOutput"]
                    self.assertNotIn("permissionDecision", output)
                    self.assertIn(text, output["additionalContext"])
                    self.assertEqual(response["systemMessage"], output["additionalContext"])

    def test_hook_is_silent_for_a_safe_command_or_another_shell(self):
        for command, shell in (("echo '====='", "/bin/zsh"), ("echo =====", "/bin/bash")):
            with self.subTest(command=command, shell=shell):
                result = run_hook(command, shell=shell)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
