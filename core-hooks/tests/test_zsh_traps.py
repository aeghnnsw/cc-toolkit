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
    "echo \"$(cat <<'EOF'\n1) a list item\nEOF\n)\"; echo ====": "====",
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
    "echo \"$(cat <<'EOF'\nDone :) now `==` is quoted\nEOF\n)\"",
    "printf '%s\\n' \"$(cat <<'EOF'\n1) Compare with \"a == b\"\nEOF\n)\"",
    "echo $'it\\'s ==x'",
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
    'PY="uv run python"; PY[1]=u; $PY -V': "$PY",
    'for line in "a b"; do set -- $line; done': "$line",
}

SPLIT_SAFE = [
    'PY="uv run python"; echo "$PY"',
    "sha=$(git rev-parse HEAD); git show $sha",
    'for f in $(git ls-files); do echo "$f"; done',
    "files=(a b c); for f in $files; do echo $f; done",
    "files=(a b c); files[1]=x; for f in $files; do echo $f; done",
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
    "ls [^b]*.txt",
    "x[1]=b; typeset -A m; m[k]=v",
]


# The Claude Code Bash safety check cannot read a zsh parameter flag, so it
# denies each command with a message about `rm` (#391). The value is the flag
# that the denial names.
FLAG_TRAPS = {
    "print -l ${(f)\"$(printf 'a\\nb')\"}": "${(f)...}",
    'x=a; echo "${(U)x}"': "${(U)...}",
    "lines=(${(@f)text})": "${(@f)...}",
    "for l in ${(f)text}; do echo $l; done": "${(f)...}",
    "echo $(echo ${(j:,:)arr})": "${(j:,:)...}",
    "[[ -n ${(f)x} ]] && echo y": "${(f)...}",
}

FLAG_SAFE = [
    "echo '${(f)x}'",
    "cat <<'EOF'\n${(f)x}\nEOF",
    "echo hi # ${(f)x}",
    "echo \\${(f)x}",
    'echo "$(echo \'${(f)x}\')"',
    "echo ${x} ${#x} ${x:-y}",
    "list='a b'; print -l ${=list}",
    "files=(a b c); print -l $files",
    "printf 'a\\nb\\n' | while read -r line; do echo $line; done",
]


# zsh can read a letter after `$NAME:` as a modifier of the variable (#391).
# The value is the text that the warning names.
MODIFIER_TRAPS = {
    "C=abc; echo $C:AGENTS.md": "$C:A",
    'C=abc; echo "$C:AGENTS.md"': "$C:A",
    "git show $SHA:README.md": "$SHA:R",
    "x=$DIR:h": "$DIR:h",
    "echo $(echo $C:t)": "$C:t",
    "cat $C:r > out.txt": "$C:r",
    "[[ -f $C:A ]] && echo y": "$C:A",
}

MODIFIER_SAFE = [
    "echo ${C}:AGENTS.md",
    "echo '$C:A'",
    "echo \\$C:A",
    "echo $C:/x $C:1 $C:-x $USER:$GROUP",
    "cat <<'EOF'\n$C:A\nEOF",
    "echo hi # $C:A",
    "echo ${C:A}",
    "echo $C: done",
]

# A test or validator command piped into `tail` or `head` while `pipefail`
# is off, so the pipeline can exit 0 when the tests fail (#458 W4-10, #391).
# The value is the (test, pager) pair that the warning names.
PIPEFAIL_TRAPS = {
    "python3 -m unittest discover -s tests -p 'test_*.py' 2>&1 | tail -5": ("unittest", "tail"),
    "pytest -q | tail -20": ("pytest", "tail"),
    (
        "uv run --no-project --python '>=3.11' python scripts/validate_packages.py"
        " --base origin/master | head -40"
    ): ("scripts/validate_packages.py", "head"),
    "python3 scripts/validate_packages.py | tail": ("scripts/validate_packages.py", "tail"),
    "uv run --with pytest-cov pytest | tail": ("pytest", "tail"),
    "uvx pytest | tail": ("pytest", "tail"),
    "python -munittest | tail": ("unittest", "tail"),
    "cd x && FOO=1 time pytest | tee log | tail -3": ("pytest", "tail"),
    ".venv/bin/py.test |& head": (".venv/bin/py.test", "head"),
    "x=$(pytest | tail)": ("pytest", "tail"),
    "(pytest | tail) &": ("pytest", "tail"),
    "set +o pipefail; pytest | tail": ("pytest", "tail"),
    "set -o pipefail; unsetopt pipefail; pytest | tail": ("pytest", "tail"),
    "pytest | tail; set -o pipefail": ("pytest", "tail"),
}

PIPEFAIL_SAFE = [
    "set -o pipefail; pytest | tail",
    "set -euo pipefail; python3 -m unittest | tail",
    "setopt PIPE_FAIL && pytest | tail",
    "setopt pipefail\npytest | head",
    "pytest | grep FAILED",
    "pytest > log; tail log",
    "pytest; tail log",
    "tail log | python -m unittest",
    "grep -rn pytest . | head",
    "git grep -n unittest | head",
    "ls .venv/bin/pytest | head",
    "uv pip install pytest | tail -1",
    "python3 -m pip install pytest | tail -1",
    "echo 'pytest | tail'",
    "cat <<'EOF'\npytest | tail\nEOF",
    "echo hi # pytest | tail",
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


def run_hook_input(input_text, shell="/bin/zsh", args=(), env=None):
    environment = os.environ.copy()
    environment["SHELL"] = shell
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=input_text,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
        timeout=30,
    )


def run_hook(command, shell="/bin/zsh", cwd=None, host=None, tool_input=None, env=None):
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {**(tool_input or {}), "command": command},
    }
    if cwd:
        payload["cwd"] = cwd
    return run_hook_input(
        json.dumps(payload), shell=shell,
        args=("--host", host) if host is not None else (), env=env,
    )


class ZshTrapTests(unittest.TestCase):
    def test_denies_an_equals_word_that_names_no_command(self):
        for command, word in EQUALS_TRAPS.items():
            with self.subTest(command=command):
                traps = zsh_traps.zsh_traps(command)
                self.assertEqual([trap.blocks for trap in traps], [True], traps)
                self.assertIn(f"`{word}` starts with `=`", traps[0].message)
                self.assertIn(f"`'{word}'`", traps[0].message)

    def test_warns_about_an_equals_word_that_names_a_command(self):
        traps = zsh_traps.zsh_traps(EQUALS_FOUND)

        self.assertEqual([trap.blocks for trap in traps], [False], traps)
        self.assertIn("`=sh` starts with `=`", traps[0].message)

    def test_warns_about_an_unsplit_variable(self):
        for command, word in SPLIT_TRAPS.items():
            with self.subTest(command=command):
                traps = zsh_traps.zsh_traps(command)
                self.assertEqual([trap.blocks for trap in traps], [False], traps)
                self.assertIn(f"variable `{word}`", traps[0].message)
                self.assertIn("define a function", traps[0].message)
                self.assertIn("with `bash`", traps[0].message)

    def test_warns_about_a_glob_that_matches_no_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = glob_directory(temp_dir)
            for command, word in GLOB_TRAPS.items():
                with self.subTest(command=command):
                    traps = zsh_traps.zsh_traps(command, directory)
                    self.assertEqual([trap.blocks for trap in traps], [False], traps)
                    self.assertIn(f"glob `{word}` matches no file", traps[0].message)

    def test_gives_no_finding_for_safe_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = glob_directory(temp_dir)
            for command in EQUALS_SAFE + SPLIT_SAFE + GLOB_SAFE:
                with self.subTest(command=command):
                    self.assertEqual(zsh_traps.zsh_traps(command, directory), [])

    def test_denies_a_zsh_parameter_flag_for_claude_code(self):
        for command, flag in FLAG_TRAPS.items():
            with self.subTest(command=command):
                traps = zsh_traps.zsh_traps(command, host="claude")
                self.assertEqual([trap.blocks for trap in traps], [True], traps)
                self.assertIn(f"flag `{flag}`", traps[0].message)
                for alternative in ("`${=list}`", "array literal", "`while read"):
                    self.assertIn(alternative, traps[0].message)

    def test_gives_no_flag_finding_for_other_hosts_or_literal_text(self):
        for command in FLAG_TRAPS:
            for host in (None, "codex"):
                with self.subTest(command=command, host=host):
                    self.assertEqual(zsh_traps.zsh_traps(command, host=host), [])
        for command in FLAG_SAFE:
            with self.subTest(command=command):
                self.assertEqual(zsh_traps.zsh_traps(command, host="claude"), [])

    def test_hook_denies_a_parameter_flag_before_the_claude_code_check(self):
        # A PreToolUse deny reaches the agent before the built-in check runs,
        # so the agent reads this reason, not the message about `rm`.
        command = "print -l ${(f)\"$(printf 'a\\nb')\"}"
        result = run_hook(command, host="claude")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("`${=list}`", output["permissionDecisionReason"])
        self.assertEqual(run_hook(command, host="codex").stdout, "")

    def test_warns_about_a_letter_after_an_unbraced_variable(self):
        for command, text in MODIFIER_TRAPS.items():
            with self.subTest(command=command):
                traps = zsh_traps.zsh_traps(command)
                self.assertEqual([trap.blocks for trap in traps], [False], traps)
                name, letter = text[1:].split(":")
                self.assertIn(f"`{text}`", traps[0].message)
                self.assertIn(f"`${{{name}}}:{letter}`", traps[0].message)

    def test_gives_no_modifier_finding_for_braced_or_literal_text(self):
        for command in MODIFIER_SAFE:
            with self.subTest(command=command):
                self.assertEqual(zsh_traps.zsh_traps(command), [])

    def test_warns_when_a_pipe_hides_the_status_of_a_test_command(self):
        for command, (test, pager) in PIPEFAIL_TRAPS.items():
            for host in (None, "claude", "codex"):
                with self.subTest(command=command, host=host):
                    traps = zsh_traps.zsh_traps(command, host=host)
                    self.assertEqual([trap.blocks for trap in traps], [False], traps)
                    self.assertIn(f"output of `{test}` goes through a pipe to `{pager}`", traps[0].message)
                    self.assertIn("`set -o pipefail;`", traps[0].message)

    def test_gives_no_pipefail_finding_with_pipefail_or_without_a_test_pipe(self):
        for command in PIPEFAIL_SAFE:
            with self.subTest(command=command):
                self.assertEqual(zsh_traps.zsh_traps(command, host="claude"), [])

    def test_skips_the_pipefail_check_for_antigravity(self):
        for command in PIPEFAIL_TRAPS:
            with self.subTest(command=command):
                self.assertEqual(zsh_traps.zsh_traps(command, host="antigravity"), [])

    @unittest.skipUnless(ZSH, "zsh is not installed")
    def test_pipefail_cases_match_zsh(self):
        # The pipe hides a failure; the fix that the warning names shows it.
        with tempfile.TemporaryDirectory() as temp_dir:
            hidden = run_zsh("false | tail -1", temp_dir)
            shown = run_zsh("set -o pipefail; false | tail -1", temp_dir)
            self.assertEqual(hidden.returncode, 0, hidden.stderr)
            self.assertNotEqual(shown.returncode, 0, shown.stderr)

    def test_hook_gives_a_pipefail_warning_without_a_decision(self):
        for host in (None, "claude", "codex"):
            with self.subTest(host=host):
                result = run_hook("pytest -q | tail -20", host=host)
                self.assertEqual(result.returncode, 0, result.stderr)
                response = json.loads(result.stdout)
                output = response["hookSpecificOutput"]
                self.assertNotIn("permissionDecision", output)
                self.assertNotIn("updatedInput", output)
                self.assertIn("set -o pipefail;", output["additionalContext"])
                self.assertEqual(response["systemMessage"], output["additionalContext"])

    @unittest.skipUnless(ZSH, "zsh is not installed")
    def test_modifier_cases_change_the_value_in_zsh(self):
        # The braced fix keeps the value; the unbraced form changes it.
        with tempfile.TemporaryDirectory() as temp_dir:
            for command in (
                "C=abc; echo $C:AGENTS.md",
                'C=abc; echo "$C:AGENTS.md"',
                "C=a/b.c; echo $C:h $C:t $C:r",
            ):
                with self.subTest(command=command):
                    braced = command.replace("$C:", "${C}:")
                    self.assertNotEqual(
                        run_zsh(command, temp_dir).stdout,
                        run_zsh(braced, temp_dir).stdout,
                    )

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

    def test_current_hosts_quote_a_separator_and_preserve_input(self):
        extra_input = {
            "description": "Print the separator",
            "timeout": 1000,
            "run_in_background": False,
            "workdir": "/tmp",
            "extension": {"keep": ["all", "fields"]},
        }
        for host in ("claude", "codex"):
            with self.subTest(host=host):
                result = run_hook("echo =====", host=host, tool_input=extra_input)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                output = json.loads(result.stdout)["hookSpecificOutput"]
                self.assertEqual(output["hookEventName"], "PreToolUse")
                self.assertEqual(
                    output.get("updatedInput"),
                    {**extra_input, "command": "echo '====='"},
                )
                self.assertNotIn("permissionDecisionReason", output)
                if host == "claude":
                    self.assertNotIn("permissionDecision", output)
                else:
                    self.assertEqual(output.get("permissionDecision"), "allow")

    @unittest.skipUnless(ZSH, "zsh is not installed")
    def test_rewritten_separators_print_literal_text_in_zsh(self):
        cases = (
            ("echo =====", "echo '====='", "=====\n"),
            ("echo =====CODEX", "echo '=====CODEX'", "=====CODEX\n"),
            ("echo ===step_2===", "echo '===step_2==='", "===step_2===\n"),
            (
                "\techo\t-n  ==  SECTION_2\t====CODEX==  \t",
                "\techo\t-n  '=='  SECTION_2\t'====CODEX=='  \t",
                "== SECTION_2 ====CODEX==",
            ),
            (" echo == ====  === \t", " echo '==' '===='  '===' \t", "== ==== ===\n"),
            ("echo a; echo =====; echo b", "echo a; echo '====='; echo b", "a\n=====\nb\n"),
            (
                "echo a && echo ===== && echo b",
                "echo a && echo '=====' && echo b",
                "a\n=====\nb\n",
            ),
            ("false || echo =====CODEX || echo b", "false || echo '=====CODEX' || echo b", "=====CODEX\n"),
            ("echo a\necho == SECTION ==\necho b", "echo a\necho '==' SECTION '=='\necho b", "a\n== SECTION ==\nb\n"),
            ("echo =====;echo ===step_2===", "echo '=====';echo '===step_2==='", "=====\n===step_2===\n"),
            ("echo a | cat; echo -n ====", "echo a | cat; echo -n '===='", "a\n===="),
            (
                "echo a; echo =====; echo \"b  c\" $# # 'quoted' after",
                "echo a; echo '====='; echo \"b  c\" $# # 'quoted' after",
                "a\n=====\nb  c 0\n",
            ),
            ("echo =====\n", "echo '====='\n", "=====\n"),
            ("\necho =====", "\necho '====='", "=====\n"),
            ("[[ -n x && -n y ]] && echo =====", "[[ -n x && -n y ]] && echo '====='", "=====\n"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            for command, rewritten, expected_stdout in cases:
                original = run_zsh(command, temp_dir)
                self.assertNotEqual(original.returncode, 0, original.stdout)
                self.assertIn("not found", original.stderr)
                for host in ("claude", "codex"):
                    with self.subTest(host=host, command=command):
                        result = run_hook(command, host=host)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        output = json.loads(result.stdout)["hookSpecificOutput"]
                        self.assertIn("updatedInput", output)
                        self.assertEqual(output["updatedInput"]["command"], rewritten)
                        actual = run_zsh(output["updatedInput"]["command"], temp_dir)
                        self.assertEqual(actual.returncode, 0, actual.stderr)
                        self.assertEqual(actual.stderr, "")
                        self.assertEqual(actual.stdout, expected_stdout)
                        checked_again = run_hook(rewritten, host=host)
                        self.assertEqual(checked_again.returncode, 0, checked_again.stderr)
                        self.assertEqual(checked_again.stdout, "")

    def test_unsupported_commands_keep_their_existing_denial(self):
        commands = (
            "echo ===== | cat",
            "echo ===== &",
            "echo ===== | cat; echo b",
            "echo a; echo ===== &",
            "echo a; echo ===== |& cat",
            "(echo a; echo =====)",
            "(echo =====); echo b",
            "{ echo =====; }",
            "if true; then echo =====; fi",
            "for i in 1; do echo =====; done",
            "case a in a) echo =====;; esac",
            "cat <<EOF\nx\nEOF\necho =====",
            "cat <<-EOF; echo =====\n\tx\n\tEOF",
            "echo a; echo ===== # note",
            "x=$(echo a; echo =====); echo b",
            "git commit -m \"$(cat <<'EOF'\nmsg\nEOF\n)\"; echo =====",
            "echo $(date) # note\necho =====",
            "printf '%s\\n' 'x; echo ====='; echo =====",
            'cat "a b"; echo =====',
            "echo $HOME; echo =====",
            "echo a\\\n; echo =====",
            "echo a; printf =====; echo b",
            "echo =====; echo ===== =sh",
            "echo =====; echo ===== | cat",
            "! echo =====; echo b",
            "echo ===== # =====",
            "echo ===== '====='",
            'echo ===== "====="',
            "echo ===\\=CODEX",
            "echo ====\\\nCODEX",
            "echo ===== $label",
            "echo ===== ${label}",
            "echo ===== $(true)",
            "echo ===== `true`",
            "echo ===== {a,b}",
            "echo ===== *.missing",
            "echo ===== > file",
            "echo ===== 2>/dev/null",
            "echo ===== <<< hi",
            "VALUE=x echo =====",
            "echo label=x =====",
            "command echo =====",
            "builtin echo =====",
            "/bin/echo =====",
            "env echo =====",
            "echo -e =====",
            "echo -n -n =====",
            "echo -- =====",
            "echo ===== -n",
            "printf ====CODEX",
            "echo ===== =sh",
            "echo ===== =/bin/sh",
            "echo ===== =missing_command_361",
            "echo ===CO-DEX",
            "echo ===é",
            "echo ====COD=EX",
            "echo ===\r",
        )
        for command in commands:
            original = run_hook(command)
            self.assertEqual(original.returncode, 0, original.stderr)
            output = json.loads(original.stdout)["hookSpecificOutput"]
            self.assertEqual(output["permissionDecision"], "deny", command)
            for host in ("claude", "codex"):
                with self.subTest(host=host, command=command):
                    result = run_hook(command, host=host)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, original.stdout)

    def test_rewrite_never_edits_text_inside_a_substitution_heredoc_or_test(self):
        # The tokenizer can read a comment, a heredoc body, an escape, or a
        # quote wrongly, and `&&` in `[[ ]]` joins conditions, not commands.
        commands = (
            "x=$(cat <<EOF # )\necho =====\nEOF\n)\necho \"$x\"",
            "x=$(echo a # )\necho =====\n); echo \"$x\"",
            "diff <(cat <<EOF # )\necho =====\nEOF\n) /dev/null",
            "cat <<E\"OF\"\necho =====\nEOF",
            "[[ a == a && echo == echo && b == b ]] && echo yes",
            # The four inputs of the focused check on PR #501.
            "[[\\\n -n a && echo == echo && -n b ]] && echo yes",
            "x=$(echo $'\\''); [[ -n ')'\\' && echo == echo && -n b ]] && echo yes",
            'x=$(echo $\'\\\'\' "\')\necho =====\n"); echo "$x"',
            'echo "${x:-"; echo =====; "}"',
            "echo \\$'\\' '; echo =====; echo '",
            "echo ${x:-'}' '; echo =====; echo '}",
            'x=$(case a in a)\necho =====\n;; esac); echo "$x"',
        )
        for command in commands:
            self.assertIsNone(zsh_traps._quote_echo_separators(command), command)
            original = run_hook(command)
            for host in ("claude", "codex"):
                with self.subTest(host=host, command=command):
                    result = run_hook(command, host=host)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, original.stdout)
                    self.assertNotIn("updatedInput", result.stdout)

    def test_unsupported_commands_preserve_other_warnings(self):
        cases = (
            ("echo ===== *.missing", "matches no file"),
            ('WORDS="a b"; echo ===== $WORDS', "does not split"),
            ("pytest | tail; echo =====", "set -o pipefail;"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            for command, warning in cases:
                for host in ("claude", "codex"):
                    with self.subTest(host=host, command=command):
                        result = run_hook(command, host=host, cwd=temp_dir)
                        output = json.loads(result.stdout)["hookSpecificOutput"]
                        self.assertEqual(output["permissionDecision"], "deny")
                        self.assertIn(warning, output["permissionDecisionReason"])
                        self.assertNotIn("updatedInput", output)

    def test_valid_equals_expansions_keep_their_existing_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir, "====CODEX")
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            env = {"PATH": temp_dir + os.pathsep + os.environ.get("PATH", "")}
            for command in ("echo =sh", "echo =====CODEX"):
                for host in ("claude", "codex"):
                    with self.subTest(host=host, command=command):
                        result = run_hook(command, host=host, env=env)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        response = json.loads(result.stdout)
                        output = response["hookSpecificOutput"]
                        self.assertNotIn("permissionDecision", output)
                        self.assertNotIn("updatedInput", output)
                        self.assertIn("Quote the word", output["additionalContext"])
                        self.assertEqual(response["systemMessage"], output["additionalContext"])
            for host in ("claude", "codex"):
                with self.subTest(host=host, mixed=True):
                    result = run_hook("echo ===== =====CODEX", host=host, env=env)
                    output = json.loads(result.stdout)["hookSpecificOutput"]
                    self.assertEqual(output["permissionDecision"], "deny")
                    self.assertNotIn("updatedInput", output)

    def test_missing_or_unknown_host_markers_keep_the_existing_denial(self):
        payload = json.dumps({
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo ====="},
            "turn_id": "incidental-host-field",
        })
        for args in ((), ("--host",), ("--host", "unknown")):
            with self.subTest(args=args):
                result = run_hook_input(payload, args=args, env={
                    "CLAUDE_PLUGIN_ROOT": "/claude/plugin",
                    "PLUGIN_ROOT": "/codex/plugin",
                })
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                output = json.loads(result.stdout)["hookSpecificOutput"]
                self.assertEqual(output["permissionDecision"], "deny")
                self.assertNotIn("updatedInput", output)

    def test_compatibility_payloads_keep_the_existing_denial(self):
        payloads = (
            {"tool_name": "exec_command", "tool_input": {"cmd": "echo ====="}},
            {"tool_name": "run_terminal_command", "tool_input": {"command": "echo ====="}},
            {"toolName": "Bash", "toolInput": {"command": "echo ====="}},
            {"tool_name": "Bash", "toolInput": {"command": "echo ====="}},
            {"toolName": "Bash", "tool_input": {"command": "echo ====="}},
        )
        for payload in payloads:
            for host in ("claude", "codex"):
                with self.subTest(host=host, payload=payload):
                    result = run_hook_input(json.dumps(payload), args=("--host", host))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = json.loads(result.stdout)["hookSpecificOutput"]
                    self.assertEqual(output["permissionDecision"], "deny")
                    self.assertNotIn("updatedInput", output)

    def test_monitor_command_gets_the_checks_but_not_the_rewrite(self):
        # The Claude Code Monitor tool runs its `command` as a shell script
        # (#527). Only a Bash command gets the `echo` rewrite.
        def run(tool, tool_input):
            payload = {
                "hook_event_name": "PreToolUse",
                "tool_name": tool,
                "tool_input": tool_input,
            }
            return run_hook_input(json.dumps(payload), args=("--host", "claude"))

        for command in ('[ "a" == "a" ]', next(iter(FLAG_TRAPS))):
            with self.subTest(command=command):
                monitor = run("Monitor", {"command": command})
                bash = run("Bash", {"command": command})
                self.assertEqual(monitor.returncode, 0, monitor.stderr)
                output = json.loads(monitor.stdout)["hookSpecificOutput"]
                self.assertEqual(output["permissionDecision"], "deny")
                self.assertEqual(
                    (monitor.returncode, monitor.stdout, monitor.stderr),
                    (bash.returncode, bash.stdout, bash.stderr),
                )
        bash = json.loads(run("Bash", {"command": "echo ====="}).stdout)
        self.assertIn("updatedInput", bash["hookSpecificOutput"])
        monitor = json.loads(run("Monitor", {"command": "echo ====="}).stdout)
        self.assertEqual(monitor["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertNotIn("updatedInput", monitor["hookSpecificOutput"])
        result = run("Monitor", {
            "ws": {"url": "wss://events.example.invalid/stream"},
            "description": "events",
            "timeout_ms": 1000,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_malformed_input_or_unrelated_tools_remain_silent(self):
        payloads = (
            "{", "null", "[]", '"text"', "{}",
            json.dumps({"tool_name": "Bash", "tool_input": None}),
            json.dumps({"tool_name": "Bash", "tool_input": ["echo ====="]}),
            json.dumps({"tool_name": "Bash", "tool_input": {"command": 42}}),
            json.dumps({"tool_name": "Bash", "tool_input": {"cmd": "echo ====="}}),
            json.dumps({"tool_name": "Read", "tool_input": {"command": "echo ====="}}),
            json.dumps({"tool_name": [], "tool_input": {"command": "echo ====="}}),
        )
        for payload in payloads:
            for args in ((), ("--host", "claude"), ("--host", "codex")):
                with self.subTest(args=args, payload=payload):
                    result = run_hook_input(payload, args=args)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(result.stdout, "")

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
            for host in (None, "claude", "codex"):
                with self.subTest(host=host, command=command, shell=shell):
                    result = run_hook(command, shell=shell, host=host)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
