import contextlib
import difflib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


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
    # Array elements, the value after `[key]=`, and parts after a `:`.
    "x=(=a b)": "=a",
    "a=(==x b)": "==x",
    "a=(b ==q9)": "==q9",
    "local -a q=(==q9)": "==q9",
    "typeset -A h=([k]=v [j]==q9)": "=q9",
    "a=([k]=v ==q9)": "==q9",
    'a=(""=q9 b)': "=q9",
    "a=($(echo ==q9))": "==q9",
    "a=(x:=q9)": "=q9",
    "a=({=q9,b})": "=q9",
    # Parts before the `=` that can expand to nothing.
    "echo ''==a": "==a",
    'echo ""==y': "==y",
    "echo $''==q9": "==q9",
    "x=; echo $x==q9": "==q9",
    'x=; echo "$x"==q9': "==q9",
    "echo $(true)==q9": "==q9",
    "echo `true`==q9": "==q9",
    'echo x >""=q9': "=q9",
    'for x in ""==q9; do :; done': "==q9",
    'case ""==q9 in *) echo m;; esac': "==q9",
    # Brace expansion.
    "echo {=a,b}": "=a",
    "echo {,=q9}": "=q9",
    "echo {a,}=q9": "=q9",
    "echo {{=q9,b},c}": "=q9",
    # Operands of a `[[ ... ]]` test.
    "[[ ==a == x ]]": "==a",
    "[[ x == ==q9 ]]": "==q9",
    "[[ -n == ]]": "==",
    "[[ == ]]": "==",
    "[[ x =~ =q9 ]]": "=q9",
    "[[ a != =q9 ]]": "=q9",
    "[[ a < =q9 ]]": "=q9",
    "[[ ! ==q9 ]]": "==q9",
    "[[ a == a && ==q9 ]]": "==q9",
    '[[ a == "]]" ]] || echo ==': "==",
    # Default words and assignment values.
    "echo ${x:-==}": "==",
    "echo a${x:-==q9}": "==q9",
    "y=${x:-==q9}": "==q9",
    "echo ${x:-${y:-==q9}}": "==q9",
    "cat <<< ${x:-==q9}": "==q9",
    "x=a:=q9": "=q9",
    "export P=/bin:=q9": "=q9",
    "x=:=q9": "=q9",
    # Subshells that start with `((`, and substitutions in arithmetic.
    "((echo a) ; echo ==); echo after": "==",
    "echo $((echo a) ; echo ==)": "==",
    "x=$(( $(echo ==q9) ))": "==q9",
    "(( $(echo ==q9) + 1 ))": "==q9",
    # A `)` that ends a `case` pattern in a substitution.
    'echo "$(case x in a) echo hi;; esac; echo ==)"': "==",
    # Redirections, prefixes, declarations, and other command forms.
    ">! out x==y": "=y",
    ">>! out x==q9": "=q9",
    # `&>!` also sends the "not found" message of zsh to the file.
    "&>! out x==q9": "=q9",
    "private X==nosuchcmd": "=nosuchcmd",
    "nocorrect x==q9": "=q9",
    "builtin local x==q9": "=q9",
    "noglob typeset x==q9": "=q9",
    "time y==q9 true": "=q9",
    "time x==q9 | cat": "=q9",
    "time x==q9 >out": "=q9",
    "for x (==q9) echo $x": "==q9",
    "function f { echo ==q9 }; f": "==q9",
    "repeat 1 echo ==q9": "==q9",
    "repeat =q9 true": "=q9",
    "echo x > {=q9,b}": "=q9",
    "case ==q9 in (x) echo m;; esac": "==q9",
    "case x in a|=q9) echo m;; esac": "=q9",
    # Assignment parts after a quoted or escaped `:`, an empty array
    # element, and substitutions or names inside `${ }`.
    'x="a:"=q9': "=q9",
    "x='a:'=q9": "=q9",
    "x=a\\:=q9": "=q9",
    "x=(); echo $x[1]==q9": "==q9",
    "echo ${${x}:-==q9}": "==q9",
    "echo ${x:-$(echo ==q9)}": "==q9",
    # A name with a `/` names a file, which is no command here.
    "printf =missing/path": "=missing/path",
    "echo =~/x": "=~/x",
    "echo =./nosuch": "=./nosuch",
    # A substitution in the body of a heredoc with an unquoted end word.
    # Quotes are text in a body, and an escaped backslash escapes no `$`.
    "cat <<EOF\n$(echo ==q9)\nEOF": "==q9",
    "cat <<-EOF\n\t$(echo ==q9)\n\tEOF": "==q9",
    "cat <<EOF\n`echo ==q9`\nEOF": "==q9",
    "cat <<EOF\n'$(echo ==q9)'\nEOF": "==q9",
    "cat <<EOF\n${x:-'$(echo ==q9)'}\nEOF": "==q9",
    "cat <<EOF\n$(( $(echo ==q9 | wc -c) ))\nEOF": "==q9",
    "cat <<EOF\n\\\\$(echo ==q9)\nEOF": "==q9",
    "cat <<EOF\n$(echo =\\\n=q9)\nEOF": "==q9",
    "x=$(cat <<EOF\n$(echo ==q9)\nEOF\n)": "==q9",
    "echo \"$(cat <<EOF\n$(echo ==q9)\nEOF\n)\"": "==q9",
    "cat <<'A' <<B\n$(echo ==q8)\nA\n$(echo ==q9)\nB": "==q9",
    "cat <<EOF\nx\\\\\n$(echo ==q9)\nEOF": "==q9",
    "cat <<EOF\n$(( '$(echo ==q9 | wc -c)' ))\nEOF": "==q9",
    # zsh ends a body only at the exact end word, and joins a line that
    # ends in a backslash with the next line.
    "cat <<EOF\n EOF\ncat <<'Y'\n$(echo ==q9)\nY\nEOF": "==q9",
    "cat <<EOF\nx\\\nEOF\ncat <<'Y'\n$(echo ==q9)\nY\nEOF": "==q9",
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
    # Assignments after `time` with no command, redirection, or pipe after
    # them, and after a `time` that does not start the pipeline.
    "time x==y",
    "time x==q9 && echo ok",
    "echo a | time x==q9",
    "! time x==q9",
    # The body of a function, the command after `repeat N` or `coproc`, and
    # the list of `for x ( )`.
    "function f { [[ a == a ]] }; f",
    "function { [[ a == a ]] }",
    "repeat 1 (( 1 == 1 ))",
    "repeat 1 [[ a == a ]]",
    "coproc [[ a == a ]]",
    "for x (a==b) echo $x",
    "for x y (a==b c d) echo $x",
    "echo $(( (1) == 1 ))",
    # A heredoc body whose end word has a quote or a backslash, an escaped
    # substitution, body text, and a quoted word or a process substitution
    # in a substitution of a body.
    "cat <<'EOF'\n$(echo ==q9)\nEOF",
    "cat <<\"EOF\"\n$(echo ==q9)\nEOF",
    "cat <<\\EOF\n$(echo ==q9)\nEOF",
    "cat <<E\"O\"F\n$(echo ==q9)\nEOF",
    "cat <<$'EOF'\n$(echo ==q9)\nEOF",
    "cat <<EOF\n\\$(echo ==q9) \\`echo ==q8\\`\nEOF",
    "cat <<EOF\n${x:-==q9} ==q8\nEOF",
    "cat <<EOF\n$(echo \"==q9\" '==q8')\nEOF",
    "cat <<EOF\n$(cat <<'X'\n==q9\nX\n)\nEOF",
    "cat <<EOF\n$(cat =(echo hi))\nEOF",
    "cat >/dev/null <<EOF\n$$(echo ==q9)\nEOF",
    "cat <<'A'\n A\ncat <<B\n$(echo ==q9)\nB\nA",
    "cat <<-'A'\n\t A\ncat <<B\n$(echo ==q9)\nB\nA",
    # Heredoc end words.
    "cat <<=EOF\nhi\n=EOF",
    "cat <<-=EOF\n\thi\n\t=EOF",
    "cat << =EOF\nhi\n=EOF",
    # A lone `=`, a quoted or escaped `=`, and words that do not start
    # with `=`.
    "[[ = ]]",
    "[[ a = = ]]",
    'echo "${x:-==q9}" ${x:-"==q9"} ${x:-\\==q9}',
    'a=(\\=q9 "=q9")',
    'echo "="q9 {"=q9",b} x{=q9,b} {=q9}',
    # The word of `?` and of a pattern operator.
    "echo ${x#==q9}",
    "echo ${x:?==q9}",
    # No brace expansion in a scalar value, and no `:` parts outside an
    # assignment, or after a quoted `=`.
    "x={=q9,b}; echo $x",
    "echo a:=q9",
    'x=a:"="q9',
    'x="a:b"=q9',
    # A pattern group in a test, and no brace expansion in a test, a `case`
    # word or pattern, or a here-string.
    "[[ a == (b|c) ]]",
    "[[ a == (=q9|c) ]]",
    "[[ {=q9,b} == a ]]",
    "case {=q9,b} in *) echo m;; esac",
    "case x in {=q9,b}) echo m;; esac",
    "cat <<< {=q9,b}",
    # Expansions that are never empty, and a quoted substitution.
    "echo $#==q9 $?==q9 ${#x}==q9 $[1]==q9 $((1))==q9",
    "echo ${x:-'$(echo ==q9)'}",
]

# zsh replaces each word with the path of `sh`; the hook denies it, with
# no corrected command.
EQUALS_FOUND = ["echo =sh", "echo =/bin/sh"]

# Each denied command and its corrected command, which has a backslash
# before the `=` of each word that names no command.
CORRECTED_COMMANDS = {
    "echo =====; ls": "echo \\=====; ls",
    "echo ===== | cat; echo === =missing_command_361": "echo \\===== | cat; echo \\=== \\=missing_command_361",
    'echo ""==y {=a,b} ${x:-==}': 'echo ""\\==y {\\=a,b} ${x:-\\==}',
    "x=(=a b); y=a:=q9; [[ ==a == x ]]": "x=(\\=a b); y=a:\\=q9; [[ \\==a == x ]]",
    "SEP=====; a[1]==x; export B===": "SEP=\\====; a[1]=\\=x; export B=\\==",
    "cat <<< === > =out": "cat <<< \\=== > \\=out",
    "x=`echo ==a` y=$(echo \"$(echo ==b)\")": "x=`echo \\==a` y=$(echo \"$(echo \\==b)\")",
    "echo ==$HOME'=='": "echo \\==$HOME'=='",
}

# Denied commands that get no corrected command. The analysis can read a
# heredoc body or end word as code, and a backslash there changes the command.
# A word that names a command, such as `=sh`, can be meant as its path.
UNCORRECTED_COMMANDS = [
    "cat <<'EOF'\n====\nEOF\necho ====",
    "cat <<=EOF\nhi $HOME\n=EOF\necho ==a",
    "echo =sh ====",
    "cat <<EOF \\\n| cat\n==a\nEOF",
    "echo $'a\\'b' && cat <<EOF\n==x\nEOF",
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

# BSD `head` and `cat`, as on macOS, reject these GNU options (#457). The
# value is the tool and the option that the warning names.
BSD_TRAPS = {
    "head -0 a.txt": ("head", "-0"),
    "head -n 0 a.txt": ("head", "-n 0"),
    "head -n0 a.txt": ("head", "-n0"),
    "head -c 0 a.txt": ("head", "-c 0"),
    "head --lines=0 a.txt": ("head", "--lines=0"),
    "printf 'a\\n' | head -n 0": ("head", "-n 0"),
    "cat -A a.txt": ("cat", "-A"),
    "cat -vET a.txt": ("cat", "-vET"),
    "cat --show-all a.txt": ("cat", "--show-all"),
    "x=$(cat -A a.txt)": ("cat", "-A"),
}

BSD_SAFE = [
    "head -5 a.txt",
    "head -n 10 a.txt",
    "head -c 100 a.txt",
    "cat -vet a.txt",
    "cat -n a.txt",
    "cat -- -A",
    "tail -n 0 a.txt",
    "echo 'cat -A a.txt'",
    "grep -n 'head -0' a.txt",
    "cat <<'EOF'\nhead -0 a.txt\nEOF",
]

# Commands that run `timeout`; the check warns when no `timeout` is on PATH.
TIMEOUT_TRAPS = ["timeout 5 make test", "cd x && timeout 5 make", "x=$(timeout 1 true)"]


def glob_directory(temp_dir):
    """Fill `temp_dir` with `a.txt` and `sub/b.md`, and return its path."""
    Path(temp_dir, "a.txt").touch()
    Path(temp_dir, "sub").mkdir()
    Path(temp_dir, "sub", "b.md").touch()
    return temp_dir


def run_zsh(command, cwd, equals=True):
    """Run `command` with zsh's default options, or with NO_EQUALS."""
    return subprocess.run(
        [ZSH, "-f", *(() if equals else ("-o", "NO_EQUALS")), "-c", command],
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

    def test_corrects_each_equals_word_that_names_no_command(self):
        for command, expected in CORRECTED_COMMANDS.items():
            with self.subTest(command=command):
                self.assertTrue(any(trap.blocks for trap in zsh_traps.zsh_traps(command)))
                self.assertEqual(zsh_traps.corrected_command(command), expected)

    @unittest.skipUnless(ZSH, "zsh is not installed")
    def test_corrected_commands_only_add_backslashes_and_run_in_zsh(self):
        commands = [*EQUALS_TRAPS, *CORRECTED_COMMANDS]
        with tempfile.TemporaryDirectory() as temp_dir:
            for command in commands:
                corrected = zsh_traps.corrected_command(command)
                if zsh_traps.HEREDOC_RE.search(command):  # a heredoc gets no corrected command
                    self.assertIsNone(corrected, command)
                    continue
                with self.subTest(command=command):
                    changes = difflib.SequenceMatcher(None, command, corrected).get_opcodes()
                    added = [corrected[j1:j2] for tag, _, _, j1, j2 in changes if tag != "equal"]
                    self.assertTrue(
                        all(tag in ("equal", "insert") for tag, *_ in changes), changes
                    )
                    self.assertEqual(set("".join(added)), {"\\"}, added)
                    self.assertFalse(
                        any(trap.blocks for trap in zsh_traps.zsh_traps(corrected))
                    )
                    result = run_zsh(corrected, temp_dir)
                    self.assertNotIn(" not found", result.stderr)

    def test_gives_no_corrected_command_that_could_be_wrong(self):
        limit = zsh_traps.MAX_CORRECTED_LENGTH
        at_limit = "echo =====" + " x" * ((limit - len("echo =====")) // 2)
        at_limit += " " * (limit - len(at_limit))
        self.assertIsNotNone(zsh_traps.corrected_command(at_limit))
        cases = [(at_limit + "x", None), ("echo ${(f)x} =====", "claude")]
        cases += [(command, None) for command in UNCORRECTED_COMMANDS]
        for command, host in cases:
            with self.subTest(command=command[:40], host=host):
                traps = zsh_traps.zsh_traps(command, host=host)
                self.assertTrue(any(trap.blocks for trap in traps), traps)
                self.assertIsNone(zsh_traps.corrected_command(command, host=host))
        # A flag blocks only in Claude Code, so other hosts get the correction.
        self.assertEqual(
            zsh_traps.corrected_command("echo ${(f)x} =====", host="codex"),
            "echo ${(f)x} \\=====",
        )
        self.assertIsNone(zsh_traps.corrected_command("echo =sh"))

    def test_denial_stays_when_the_correction_fails(self):
        traps = zsh_traps.zsh_traps("echo =====")
        with mock.patch.object(zsh_traps, "corrected_command", side_effect=ValueError):
            message = zsh_traps._trap_message(traps, "echo =====", None, None)
        self.assertEqual(message, traps[0].message)

    def test_denies_an_equals_word_that_names_a_command(self):
        for command in EQUALS_FOUND:
            with self.subTest(command=command):
                traps = zsh_traps.zsh_traps(command)
                word = command.split()[-1]
                self.assertEqual([trap.blocks for trap in traps], [True], traps)
                self.assertIn(f"`{word}` starts with `=`", traps[0].message)
                self.assertIn(f"path of the command `{word[1:]}`", traps[0].message)
                self.assertIn(f"`$(command -v {word[1:]})`", traps[0].message)
                self.assertIsNone(zsh_traps.corrected_command(command))

    def test_denies_substitutions_nested_deeper_than_the_check_reads(self):
        depth = zsh_traps.MAX_NESTED_SHELL_DEPTH + 2
        deep = "echo " + "$(" * depth + "printf ==z" + ")" * depth
        traps = zsh_traps.zsh_traps(deep)
        self.assertEqual([trap.blocks for trap in traps], [True], traps)
        self.assertIn("levels deep", traps[0].message)
        self.assertIsNone(zsh_traps.corrected_command(deep))
        # Without an `=` in the unread text, no word can start with `=`.
        self.assertEqual(zsh_traps.zsh_traps(deep.replace("==z", "z")), [])
        # The same substitutions in a heredoc body give the same denial.
        traps = zsh_traps.zsh_traps(f"cat <<EOF\n{deep}\nEOF")
        self.assertEqual([trap.blocks for trap in traps], [True], traps)
        self.assertIn("levels deep", traps[0].message)
        if ZSH:
            with tempfile.TemporaryDirectory() as temp_dir:
                self.assertIn(" not found", run_zsh(deep, temp_dir).stderr)

    def test_hook_denies_a_command_that_it_fails_to_read(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hi"}})
        for host in ("claude", "codex", "antigravity"):
            with self.subTest(host=host):
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(zsh_traps, "_analyze", side_effect=RecursionError), \
                        mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                        mock.patch.object(sys, "argv", ["zsh_traps.py", "--host", host]), \
                        mock.patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
                        contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                        self.assertRaises(SystemExit) as exit_status:
                    zsh_traps.main()
                steps = zsh_traps.TURN_OFF_PLUGIN_STEPS.get(
                    host, zsh_traps.TURN_OFF_PLUGIN_STEPS[None]
                )
                if host == "antigravity":
                    self.assertEqual(exit_status.exception.code, zsh_traps.block_status(host))
                    message = stderr.getvalue()
                else:
                    self.assertEqual(exit_status.exception.code, 0)
                    output = json.loads(stdout.getvalue())["hookSpecificOutput"]
                    self.assertEqual(output["permissionDecision"], "deny")
                    message = output["permissionDecisionReason"]
                self.assertIn("failed to read the command (RecursionError", message)
                self.assertIn(steps, message)

    def test_reads_many_brace_alternatives_quickly(self):
        # Brace expansion doubles the words for each `{,}`; the check must
        # not do the same.
        command = "echo " + "{,}" * 40 + "=q9"
        started = time.monotonic()
        traps = zsh_traps.zsh_traps(command)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual([trap.blocks for trap in traps], [True], traps)

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

    def test_warns_about_a_gnu_option_that_bsd_tools_reject(self):
        for command, (tool, option) in BSD_TRAPS.items():
            for host in (None, "claude", "codex"):
                with self.subTest(command=command, host=host):
                    traps = zsh_traps.zsh_traps(command, host=host)
                    self.assertEqual([trap.blocks for trap in traps], [False], traps)
                    expected = f"`head {option}`" if tool == "head" else f"option `{option}`"
                    self.assertIn(expected, traps[0].message)

    def test_gives_no_bsd_finding_for_bsd_options_or_literal_text(self):
        for command in BSD_SAFE:
            with self.subTest(command=command):
                self.assertEqual(zsh_traps.zsh_traps(command, host="claude"), [])

    def test_skips_the_head_and_cat_checks_for_antigravity(self):
        # GNU tools accept these options, so the check must not block them.
        for command in BSD_TRAPS:
            with self.subTest(command=command):
                self.assertEqual(zsh_traps.zsh_traps(command, host="antigravity"), [])

    @unittest.skipUnless(sys.platform == "darwin", "the BSD head and cat ship with macOS")
    def test_bsd_cases_fail_with_the_macos_tools(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "a.txt").write_text("a\tb\n")
            for command in BSD_TRAPS:
                with self.subTest(command=command):
                    bsd = command.replace("head ", "/usr/bin/head ").replace("cat ", "/bin/cat ")
                    result = subprocess.run(["/bin/sh", "-c", bsd], text=True, capture_output=True,
                                            cwd=temp_dir, check=False, timeout=30)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("illegal", result.stderr)
            fix = subprocess.run(["/bin/cat", "-vet", "a.txt"], text=True, capture_output=True,
                                 cwd=temp_dir, check=True, timeout=30)
            self.assertEqual(fix.stdout, "a^Ib$\n")

    def test_warns_about_timeout_only_without_a_timeout_command(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(os.environ, {"PATH": temp_dir}):
            for command in TIMEOUT_TRAPS:
                for host in (None, "claude", "codex", "antigravity"):
                    with self.subTest(command=command, host=host):
                        traps = zsh_traps.zsh_traps(command, host=host)
                        if host == "antigravity":  # An Antigravity hook cannot warn without blocking.
                            self.assertEqual(traps, [])
                            continue
                        self.assertEqual([trap.blocks for trap in traps], [False], traps)
                        self.assertIn("no `timeout` command is on PATH", traps[0].message)
            self.assertEqual(zsh_traps.zsh_traps("make timeout; echo 'timeout 5'; /opt/bin/timeout 5 x"), [])
            executable = Path(temp_dir, "timeout")
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            for command in TIMEOUT_TRAPS:
                with self.subTest(command=command, on_path=True):
                    self.assertEqual(zsh_traps.zsh_traps(command), [])

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
        # zsh expands an `=` word when the command runs differently with the
        # EQUALS option on, its default, and off.
        cases = [(command, True) for command in EQUALS_TRAPS]
        cases += [(command, False) for command in EQUALS_SAFE + EQUALS_FOUND]
        with tempfile.TemporaryDirectory() as temp_dir:
            for command, fails in cases:
                with self.subTest(command=command):
                    result = run_zsh(command, temp_dir)
                    unexpanded = run_zsh(command, temp_dir, equals=False)
                    self.assertEqual(
                        " not found" in result.stderr, fails and "&>" not in command,
                        result.stderr,
                    )
                    self.assertNotIn(" not found", unexpanded.stderr)
                    runs = [(run.returncode, run.stdout, run.stderr) for run in (result, unexpanded)]
                    expands = command in EQUALS_TRAPS or command in EQUALS_FOUND
                    self.assertEqual(runs[0] != runs[1], expands, runs)

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

    def test_each_host_gets_the_corrected_command_in_the_denial(self):
        # The separator rewrite skips a pipeline, so each host denies it.
        command = "echo ===== | cat"
        expected = "Run it as it is:\necho \\===== | cat"
        for host in (None, "claude", "codex"):
            with self.subTest(host=host):
                result = run_hook(command, host=host)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)["hookSpecificOutput"]
                self.assertEqual(output["permissionDecision"], "deny")
                self.assertTrue(output["permissionDecisionReason"].endswith(expected))
        result = run_hook(command, host="antigravity")
        self.assertEqual(result.returncode, zsh_traps.block_status("antigravity"), result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.rstrip("\n").endswith(expected), result.stderr)

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

    def test_valid_equals_expansions_are_denied_without_a_corrected_command(self):
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
                        self.assertEqual(output["permissionDecision"], "deny")
                        self.assertNotIn("updatedInput", output)
                        reason = output["permissionDecisionReason"]
                        self.assertIn("$(command -v ", reason)
                        self.assertNotIn("Corrected command", reason)
                        self.assertEqual(response["systemMessage"], reason)
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
            for command, text in (
                ("ls *.md", "matches no file"), ("cat -A a.txt", "`cat -vet`"),
            ):
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
