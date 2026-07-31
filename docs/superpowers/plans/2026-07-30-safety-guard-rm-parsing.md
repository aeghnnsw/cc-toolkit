# Safety Guard `rm` Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix issue #181 by limiting safety checks to real `rm` invocations, permitting explicit macOS per-user temp-file cleanup, and reporting the matched safety rule.

**Architecture:** Tokenize shell input with `shlex`, divide it into command segments, and extract only direct `rm` invocations plus supported wrappers. Classify only removal targets, with a strict-descendant exception for the active temporary directory and reason-returning safety checks for actionable errors.

**Tech Stack:** Python 3.8+ standard library (`shlex`, `tempfile`, `pathlib`, `unittest`), Claude/Codex hook JSON, plugin manifest JSON

## Global Constraints

- Add no runtime dependency; the hook must continue to run with `uv run --no-project`.
- Preserve both `Bash.command` and `exec_command.cmd` payload support.
- Preserve the public boolean helper `is_dangerous_rm_command(command)`.
- Continue blocking actual wildcards, root/current/parent/home targets, and protected system paths.
- Permit only strict descendants of the active temp root; never permit deleting the root itself.
- Keep changes limited to issue #181 and bump `core-hooks` by one patch version.

## Review Hardening Addendum

PR review exposed safety regressions that the initial simplified parsing
sketches below did not cover. The implemented parser therefore also:

- removes line continuations and shell comments quote-aware, preserves quoted
  punctuation, and distinguishes redirections from command boundaries;
- consumes clustered and value-taking options for supported wrappers;
- recognizes common process launchers, `xargs`, `find -exec`, `eval`,
  shell/fish command strings, `env -S`, and command/process substitutions;
- treats `env -S` as argv splitting, not shell evaluation;
- classifies protected `find` roots substituted into direct
  `find -exec rm ... {}` targets;
- rejects `/`, ancestors of protected roots, and non-exact macOS temp-root
  shapes as trusted temp directories;
- normalizes repeated slashes in absolute removal targets and compares
  executable basenames case-insensitively for default macOS filesystems;
- fails closed when an unexpected parser exception reaches the public analysis
  boundary, because the command cannot be classified safely.

These decisions supersede the narrower wrapper and tokenization snippets later
in this historical implementation plan. Arbitrary launcher semantics and data
flow into `xargs` through standard input remain out of scope.

---

### Task 1: Invocation-aware `rm` safety guard

**Files:**
- Modify: `core-hooks/tests/test_safety_guard.py`
- Modify: `core-hooks/scripts/safety_guard.py`
- Modify: `core-hooks/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: hook payloads accepted by `get_shell_command(tool_name, tool_input)`.
- Produces: `dangerous_rm_reason(command) -> str or None`; preserves `is_dangerous_rm_command(command) -> bool`.

- [ ] **Step 1: Expand the hook test helpers and add failing issue regressions**

Update `run_hook` to accept environment overrides:

```python
import os


def run_hook(payload, env=None):
    process_env = os.environ.copy()
    process_env.update(env or {})
    with tempfile.TemporaryDirectory() as temp_dir:
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=temp_dir,
            env=process_env,
            check=False,
        )
```

Add helpers on `SafetyGuardTests`:

```python
def run_command(self, command, tool_name="exec_command", env=None):
    input_key = "command" if tool_name == "Bash" else "cmd"
    return run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {input_key: command},
        },
        env=env,
    )

def assert_allowed(self, command, tool_name="exec_command", env=None):
    result = self.run_command(command, tool_name=tool_name, env=env)
    self.assertEqual(result.returncode, 0, result.stderr)

def assert_blocked(self, command, reason, tool_name="exec_command", env=None):
    result = self.run_command(command, tool_name=tool_name, env=env)
    self.assertEqual(result.returncode, 2, result.stderr)
    self.assertIn("BLOCKED", result.stderr)
    self.assertIn(f"Reason: {reason}", result.stderr)
```

Add regression and safety cases:

```python
def test_allows_explicit_file_beneath_macos_tmpdir(self):
    temp_root = "/var/folders/8n/example/T"
    self.assert_allowed(
        f"rm {temp_root}/candidate.json",
        env={"TMPDIR": temp_root},
    )

def test_blocks_macos_tmpdir_root_itself(self):
    temp_root = "/var/folders/8n/example/T"
    self.assert_blocked(
        f"rm -rf {temp_root}",
        "temporary directory root",
        env={"TMPDIR": temp_root},
    )

def test_blocks_parent_traversal_from_macos_tmpdir(self):
    temp_root = "/var/folders/8n/example/T"
    self.assert_blocked(
        f"rm {temp_root}/../outside",
        "parent directory reference",
        env={"TMPDIR": temp_root},
    )

def test_does_not_trust_broad_protected_tmpdir(self):
    cases = (
        ("/var", "/var/log/example"),
        ("/var/folders", "/var/folders/example"),
        ("/var/log/example/T", "/var/log/example/T/candidate.json"),
    )
    for temp_root, target in cases:
        with self.subTest(temp_root=temp_root):
            self.assert_blocked(
                f"rm -rf {target}",
                "protected system path /var",
                env={"TMPDIR": temp_root},
            )

def test_allows_glob_in_later_command(self):
    self.assert_allowed("rm /tmp/a.txt /tmp/b.txt && ls /tmp/prefix*")

def test_allows_rm_text_in_quoted_issue_title(self):
    self.assert_allowed(
        'gh issue create --title "safety_guard blocks rm under /var/folders"'
    )

def test_blocks_wildcard_owned_by_rm(self):
    self.assert_blocked("rm -rf /tmp/prefix*", "wildcard rm target")

def test_blocks_protected_system_target_after_separator(self):
    self.assert_blocked(
        "echo ready && rm -rf /var/log/example",
        "protected system path /var",
    )

def test_blocks_protected_system_target_through_sudo(self):
    self.assert_blocked(
        "sudo rm -rf /var/log/example",
        "protected system path /var",
    )

def test_blocks_protected_system_target_through_env(self):
    self.assert_blocked(
        "env MODE=test rm -rf /var/log/example",
        "protected system path /var",
    )

def test_blocks_rm_after_shell_boundaries(self):
    commands = (
        "echo ready && rm /var/log/example",
        "false || rm /var/log/example",
        "echo ready; rm /var/log/example",
        "echo ready | rm /var/log/example",
        "echo ready\nrm /var/log/example",
        "(rm /var/log/example)",
        "echo `rm /var/log/example`",
    )
    for command in commands:
        with self.subTest(command=command):
            self.assert_blocked(command, "protected system path /var")

def test_blocks_supported_rm_program_forms(self):
    commands = (
        "command rm /var/log/example",
        "/bin/rm /var/log/example",
        "MODE=test rm /var/log/example",
    )
    for command in commands:
        with self.subTest(command=command):
            self.assert_blocked(command, "protected system path /var")

def test_blocks_rm_inside_shell_command_string(self):
    commands = (
        'bash -c "rm /var/log/example"',
        'sudo sh -c "rm /var/log/example"',
        'env MODE=test zsh -lc "rm /var/log/example"',
    )
    for command in commands:
        with self.subTest(command=command):
            self.assert_blocked(command, "protected system path /var")

def test_blocks_rm_inside_shell_group_or_function(self):
    commands = (
        "{ rm /var/log/example; }",
        "cleanup() { rm /var/log/example; }; cleanup",
        "function cleanup { rm /var/log/example; }; cleanup",
    )
    for command in commands:
        with self.subTest(command=command):
            self.assert_blocked(command, "protected system path /var")

def test_blocks_rm_inside_double_quoted_command_substitution(self):
    commands = (
        'echo "$(rm /var/log/example)"',
        'echo "`rm /var/log/example`"',
    )
    for command in commands:
        with self.subTest(command=command):
            self.assert_blocked(command, "protected system path /var")

def test_allows_rm_text_inside_single_quotes(self):
    commands = (
        "echo '$(rm /var/log/example)'",
        "echo '`rm /var/log/example`'",
    )
    for command in commands:
        with self.subTest(command=command):
            self.assert_allowed(command)

def test_blocks_malformed_rm_shell_text(self):
    self.assert_blocked(
        'rm "/var/log/example',
        "unparseable rm command",
    )

def test_allows_explicit_tmp_file_for_claude_bash(self):
    self.assert_allowed("rm /tmp/candidate.json", tool_name="Bash")

def test_blocks_existing_protected_target_categories(self):
    cases = (
        ("rm -rf /", "root directory"),
        ("rm -rf .", "current directory target"),
        ("rm -rf ..", "parent directory reference"),
        ("rm -rf ~", "home directory target"),
        ("rm -rf $HOME/work", "home directory target"),
        ("rm -rf /usr/local/example", "protected system path /usr"),
        ("rm -rf /var/log/example", "protected system path /var"),
        ("rm -rf /etc/example", "protected system path /etc"),
        ("rm -rf /bin/example", "protected system path /bin"),
        ("rm -rf /sbin/example", "protected system path /sbin"),
        ("rm -rf /lib/example", "protected system path /lib"),
        ("rm -rf /opt/example", "protected system path /opt"),
        ("rm -rf /sys/example", "protected system path /sys"),
        ("rm -rf /proc/example", "protected system path /proc"),
        ("rm -rf /dev/example", "protected system path /dev"),
        ("rm -rf /boot/example", "protected system path /boot"),
    )
    for command, reason in cases:
        with self.subTest(command=command):
            self.assert_blocked(command, reason)
```

Retain the existing hook matcher test.

- [ ] **Step 2: Run the expanded tests and verify the regressions fail**

Run:

```bash
python3 -m unittest core-hooks/tests/test_safety_guard.py -v
```

Expected: the new macOS temp, trailing-glob, quoted-text, wrapper, malformed
input, and reason-message assertions fail against the current whole-string
regex implementation; the two original tests remain green.

- [ ] **Step 3: Implement shell segmentation and real-invocation extraction**

In `core-hooks/scripts/safety_guard.py`, add `os`, `shlex`, and `tempfile`
imports. Replace whole-command normalization with these focused helpers:

```python
SHELL_PUNCTUATION = ";&|()<>\n`"
CONTROL_PREFIXES = {"!", "if", "then", "elif", "else", "while", "until", "do"}
SIMPLE_WRAPPERS = {"command", "exec", "nohup", "time"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _shell_tokens(command):
    lexer = shlex.shlex(
        command,
        posix=True,
        punctuation_chars=SHELL_PUNCTUATION,
    )
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _is_boundary(token):
    return token and all(character in SHELL_PUNCTUATION for character in token)


def _command_segments(tokens):
    segment = []
    in_comment = False
    for token in tokens:
        if in_comment:
            if "\n" in token:
                if segment:
                    yield segment
                    segment = []
                in_comment = False
            continue
        if token.startswith("#"):
            in_comment = True
        elif _is_boundary(token):
            if segment:
                yield segment
                segment = []
        else:
            segment.append(token)
    if segment:
        yield segment
```

Implement `_rm_arguments(segment)` so it:

1. skips shell control prefixes and leading `NAME=value` assignments;
2. unwraps `command`, `exec`, `nohup`, and `time`;
3. unwraps `env` plus its assignments/options;
4. unwraps `sudo` plus its options, including separate values for `-u`,
   `-g`, `-h`, `-p`, `-C`, `-r`, and `-t`;
5. recognizes both `rm` and an explicit path whose basename is `rm`;
6. returns only the tokens after that executable, or `None` for any other
   command segment.

Use these exact helpers:

```python
SUDO_VALUE_OPTIONS = {
    "-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt",
    "-C", "--chdir", "-r", "--role", "-t", "--type",
}
ENV_VALUE_OPTIONS = {"-u", "--unset", "-C", "--chdir"}


def _program_name(token):
    return token.rsplit("/", 1)[-1]


def _skip_wrapper_options(tokens, index, value_options):
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if ASSIGNMENT_RE.match(token):
            index += 1
            continue
        if not token.startswith("-") or token == "-":
            return index
        option = token.split("=", 1)[0]
        index += 1
        if (
            option in value_options
            and "=" not in token
            and index < len(tokens)
        ):
            index += 1
    return index


def _rm_arguments(segment):
    index = 0
    while index < len(segment) and segment[index] in CONTROL_PREFIXES:
        index += 1
    while index < len(segment) and ASSIGNMENT_RE.match(segment[index]):
        index += 1

    while index < len(segment):
        program = _program_name(segment[index])
        if program in SIMPLE_WRAPPERS:
            index = _skip_wrapper_options(segment, index + 1, set())
        elif program == "env":
            index = _skip_wrapper_options(
                segment,
                index + 1,
                ENV_VALUE_OPTIONS,
            )
        elif program == "sudo":
            index = _skip_wrapper_options(
                segment,
                index + 1,
                SUDO_VALUE_OPTIONS,
            )
        else:
            break

    if index < len(segment) and _program_name(segment[index]) == "rm":
        return segment[index + 1:]
    return None
```

Use `_command_segments(_shell_tokens(command))` to yield each real invocation's
argument list. This must recognize dangerous commands after `&&`, `||`, `;`,
pipelines, newlines, subshell boundaries, and backticks without treating an
argument to `echo`, `gh`, `grep`, or `git commit` as an executable.

Recognize `bash`, `dash`, `fish`, `ksh`, `sh`, and `zsh` after the same wrapper
processing. When one has a short option containing `c`, recursively pass its
following command-string argument through `dangerous_rm_reason`, with a maximum
nesting depth of eight. This preserves safety for `bash -c "rm /var/..."` while
leaving quoted prose passed to non-shell programs untouched.

Before segment inspection, scan the original shell text for `$()` and backtick
command substitutions outside single quotes. Recursively inspect their command
content so double quoting does not hide executable deletion, while single
quotes continue to represent literal prose.

- [ ] **Step 4: Implement target classification and actionable reasons**

Extract removal targets by skipping options until `--` and then treating all
remaining tokens as targets:

```python
def _rm_targets(arguments):
    options_finished = False
    for argument in arguments:
        if not options_finished and argument == "--":
            options_finished = True
        elif not options_finished and argument.startswith("-") and argument != "-":
            continue
        else:
            yield argument
```

Define the protected roots:

```python
PROTECTED_SYSTEM_PATHS = (
    "/usr", "/var", "/private/var", "/etc", "/bin", "/sbin", "/lib",
    "/opt", "/sys", "/proc", "/dev", "/boot",
)
```

Add temp-root helpers that collect absolute roots from `TMPDIR` and
`tempfile.gettempdir()`, normalize them with `Path.resolve(strict=False)`, and
compare candidates using `Path.relative_to`. Reject temp roots inside protected
system trees unless they resolve to the macOS per-user
`/var/folders/<id>/<id>/T` shape. Return these exact reasons:

```python
"wildcard rm target"
"root directory"
"current directory target"
"parent directory reference"
"home directory target"
"temporary directory root"
"protected system path <matched-root>"
"unparseable rm command"
```

Implement containment and target classification as follows:

```python
def _resolved_absolute_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        return None
    return path.resolve(strict=False)


def _temp_roots():
    roots = []
    for value in (os.environ.get("TMPDIR"), tempfile.gettempdir()):
        if not value:
            continue
        root = _resolved_absolute_path(value)
        if root is not None and root not in roots:
            roots.append(root)
    return roots


def _temp_relationship(target):
    candidate = _resolved_absolute_path(target)
    if candidate is None:
        return None
    roots = _temp_roots()
    if candidate in roots:
        return "root"
    for root in roots:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        return "descendant"
    return None


def _dangerous_target_reason(target):
    if "*" in target:
        return "wildcard rm target"

    normalized = target.rstrip("/") or "/"
    lowered = normalized.lower()
    if normalized == "/":
        return "root directory"
    if normalized == ".":
        return "current directory target"
    if ".." in target.split("/"):
        return "parent directory reference"
    if (
        lowered.startswith("~")
        or "$home" in lowered
        or "${home}" in lowered
    ):
        return "home directory target"

    temp_relationship = _temp_relationship(target)
    if temp_relationship == "root":
        return "temporary directory root"
    if temp_relationship == "descendant":
        return None

    for protected in PROTECTED_SYSTEM_PATHS:
        if lowered == protected or lowered.startswith(protected + "/"):
            return f"protected system path {protected}"
    return None
```

`dangerous_rm_reason(command)` must:

1. tokenize the command and conservatively return `"unparseable rm command"`
   when `shlex` raises `ValueError` and raw text contains `rm` as a word;
2. inspect only targets from extracted `rm` invocations;
3. check wildcard, root/current/parent/home rules before temp containment;
4. allow a resolved path strictly below an active temp root;
5. otherwise block a protected path only when it equals the protected root or
   begins with `<root>/`.

Preserve the boolean interface:

```python
def dangerous_rm_reason(command):
    try:
        segments = _command_segments(_shell_tokens(command))
        for segment in segments:
            arguments = _rm_arguments(segment)
            if arguments is None:
                continue
            for target in _rm_targets(arguments):
                reason = _dangerous_target_reason(target)
                if reason:
                    return reason
    except ValueError:
        if re.search(r"\brm(?:\s|$)", command, re.IGNORECASE):
            return "unparseable rm command"
    return None


def is_dangerous_rm_command(command):
    return dangerous_rm_reason(command) is not None
```

In `main()`, use the reason once and print it:

```python
reason = dangerous_rm_reason(command) if command else None
if reason:
    print("BLOCKED: Potentially dangerous rm command detected", file=sys.stderr)
    print(f"Reason: {reason}", file=sys.stderr)
    print(
        "Safe explicit removals like 'rm -rf specific_folder' are allowed",
        file=sys.stderr,
    )
    sys.exit(2)
```

- [ ] **Step 5: Run the focused suite and verify it passes**

Run:

```bash
python3 -m unittest core-hooks/tests/test_safety_guard.py -v
```

Expected: all safety-guard tests pass with zero failures.

- [ ] **Step 6: Bump the plugin patch version**

Change `core-hooks/.claude-plugin/plugin.json`:

```json
{
  "name": "core-hooks",
  "description": "Core safety and workflow hooks for Claude Code",
  "version": "1.0.11"
}
```

- [ ] **Step 7: Verify code, JSON, and regression behavior**

Run:

```bash
python3 -m unittest discover -s core-hooks/tests -p 'test_*.py' -v
jq . core-hooks/.claude-plugin/plugin.json
jq . .claude-plugin/marketplace.json
git diff --check
```

Expected: all tests pass, both JSON files parse, and `git diff --check`
produces no output.

Manually invoke the reason helper for the three issue examples and one real
system target. Expected results:

```text
macos_tmp_file: None
glob_in_following_ls: None
rm_only_in_issue_title: None
system_var: protected system path /var
```

- [ ] **Step 8: Commit the implementation**

```bash
git add core-hooks/scripts/safety_guard.py \
  core-hooks/tests/test_safety_guard.py \
  core-hooks/.claude-plugin/plugin.json
git commit -m "fix: scope safety guard to rm invocations"
```

### Task 2: Final branch review and pull request

**Files:**
- Verify: all files changed from `origin/master`

**Interfaces:**
- Consumes: the passing issue #181 implementation commit.
- Produces: a pushed issue branch and a ready pull request closing #181.

- [ ] **Step 1: Review the complete branch**

Run:

```bash
git diff --stat origin/master...HEAD
git diff --check origin/master...HEAD
git status --short --branch
```

Expected: only the design, plan, safety guard, safety tests, and core-hooks
manifest changed; the worktree is clean.

- [ ] **Step 2: Re-run final verification**

Run:

```bash
python3 -m unittest discover -s core-hooks/tests -p 'test_*.py' -v
jq . core-hooks/.claude-plugin/plugin.json
jq . .claude-plugin/marketplace.json
```

Expected: all tests pass and both JSON files parse.

- [ ] **Step 3: Push and create the pull request**

```bash
git push -u origin bugfix-181-safety-guard-macos-temp
gh pr create \
  --title "Fix safety guard rm parsing" \
  --body "Scope safety checks to real rm invocations and allow explicit cleanup beneath the active macOS temp directory.

Closes #181"
```

Expected: GitHub returns the URL of a ready pull request targeting `master`.
