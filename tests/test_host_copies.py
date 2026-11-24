"""The host copies of each skill: files, text, frontmatter, invocation policy, and tool names.

CONTRIBUTING.md, "Skills for more than one host", sets the rules. The Claude copy is the reference.
A Codex or Antigravity copy differs from it only where an allowlist at the end of this module says so:

- HOST_FILES: the files that only one copy has.
- HOST_LINES: the lines that differ in a shared file, as `-` (Claude copy) and `+` (host copy) lines.
  The lines, with their repeats, must equal the entry, so a new difference fails and so does an entry
  line that no longer differs. A `#` line in an entry is a comment.
- UNMATCHED: the files whose text the test does not compare yet, each with its repair issue. The entry
  fails when the file differs only in the lines that HOST_LINES lists for it, or not at all.
- INVOCATION_EXCEPTIONS: the copies whose invocation policy does not agree yet, each with its repair issue.
"""
from collections import Counter, defaultdict
import difflib
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, git_files
from test_skill_links import discover

FRONTMATTER_FIELD = re.compile(r'^([A-Za-z][\w-]*):\s*(.*)$')
# The frontmatter keys that each host allows; a host that is not listed allows any key (CONTRIBUTING.md,
# "Frontmatter").
ALLOWED_KEYS = {'codex': {'name', 'description'},
        'antigravity': {'name', 'description', 'disable-model-invocation'}}
CODEX_POLICY = 'agents/openai.yaml'
# Tool names and wording that a copy for another host must not use (CONTRIBUTING.md, "Antigravity copies").
CLAUDE_TOOLS = ('AskUserQuestion', 'Skill tool', 'TodoWrite', 'subagent_type', 'SendMessage', 'WebSearch',
                'WebFetch', 'run_in_background', 'CLAUDE_PLUGIN_ROOT')
CODEX_TOOLS = ('update_plan', 'spawn_agent', 'request_user_input')
OTHER_HOST_WORDING = ('In Claude Code', 'PR monitoring mechanism', 'In Codex', '--host codex')
BLOCKED_TERMS = {'codex': CLAUDE_TOOLS, 'antigravity': CLAUDE_TOOLS + CODEX_TOOLS + OTHER_HOST_WORDING}


def skill_copies(registrations):
    """Return {(plugin, skill): {host: folder}} for each skill that more than one host discovers."""
    found = defaultdict(dict)
    for package, _, skills in registrations:
        for skill in skills:
            found[package.source, skill.parent.name][package.host] = skill.parent
    return {key: hosts for key, hosts in sorted(found.items()) if len(set(hosts.values())) > 1}


def relative(path):
    return path.relative_to(ROOT).as_posix()


def copy_files(folder, files):
    prefix = relative(folder) + '/'
    return {name[len(prefix):] for name in files if name.startswith(prefix) and (ROOT / name).is_file()}


def read_lines(path):
    """Return the lines of a file. A `\r` line ending stays in its line, and a final newline gives a last
    empty line, so equal lines mean equal bytes."""
    return path.read_text(encoding='utf-8', newline='').split('\n')


def split_skill(path):
    """Return the frontmatter fields, unquoted, and the body lines of a SKILL.md file."""
    lines = read_lines(path)
    end = lines.index('---', 1)
    fields = {}
    for line in lines[1:end]:
        match = FRONTMATTER_FIELD.match(line)
        if match:
            fields[match[1]] = match[2].strip().strip('"\'')
    return fields, lines[end + 1:]


def compared_lines(path):
    """Return the lines to compare: for SKILL.md, the description line and the body."""
    if path.name == 'SKILL.md':
        fields, body = split_skill(path)
        return [f'description: {fields.get("description", "")}', *body]
    return read_lines(path)


def changed_lines(claude, host):
    """Count the lines that differ, as `-` lines of the Claude copy and `+` lines of the host copy."""
    claude = [line.replace('${CLAUDE_PLUGIN_ROOT}', '<plugin-root>') for line in claude]
    changed = Counter()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, claude, host, autojunk=False).get_opcodes():
        if tag != 'equal':
            changed.update('-' + line for line in claude[i1:i2])
            changed.update('+' + line for line in host[j1:j2])
    return changed


def allowed_lines(path):
    """Count the `-` and `+` lines that HOST_LINES lists for a host file."""
    return Counter(line for line in HOST_LINES.get(path, '').splitlines() if line and not line.startswith('#'))


def user_invoked(host, folder):
    """Return whether the copy sets the user-invoked policy of its host."""
    if host == 'codex':
        policy = folder / CODEX_POLICY
        section = None
        for line in policy.read_text(encoding='utf-8').splitlines() if policy.is_file() else ():
            if line and not line[0].isspace():
                section, _, rest = line.partition(':')
                if section == 'policy' and re.search(r'\ballow_implicit_invocation:\s*false\b', rest):
                    return True  # The flow form: policy: {allow_implicit_invocation: false}
            elif section == 'policy' and re.match(r'\s+allow_implicit_invocation:\s*false\b', line):
                return True
        return False
    return split_skill(folder / 'SKILL.md')[0].get('disable-model-invocation') == 'true'


class HostCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registrations = discover()
        cls.copies = skill_copies(cls.registrations)
        cls.files = git_files(ROOT)

    def pairs(self):
        """Yield (copy name, host, Claude folder, host folder) for each copy that is not the Claude copy."""
        for hosts in self.copies.values():
            for host, folder in hosts.items():
                if 'claude' in hosts and folder != hosts['claude']:
                    yield relative(folder), host, hosts['claude'], folder

    def test_skills_with_copies_are_found(self):
        self.assertEqual(set(self.copies[('dev-skills', 'repo-cleanup')]), {'claude', 'codex', 'antigravity'})
        for (plugin, skill), hosts in self.copies.items():
            with self.subTest(skill=f'{plugin}/{skill}'):
                self.assertIn('claude', hosts, 'the test compares each copy with the Claude copy; add one')

    def test_copies_have_the_same_files(self):
        for name, host, claude, folder in self.pairs():
            claude_files, host_files = copy_files(claude, self.files), copy_files(folder, self.files)
            found = {'-' + path for path in claude_files - host_files}
            found |= {'+' + path for path in host_files - claude_files}
            if host == 'codex':
                found.discard('+' + CODEX_POLICY)
            with self.subTest(copy=name):
                self.assertEqual(found, HOST_FILES.get(name, set()),
                                 'a file is only in one copy; add it to the other copies or list it in HOST_FILES')

    def test_shared_files_differ_only_in_host_lines(self):
        for name, host, claude, folder in self.pairs():
            for path in sorted(copy_files(claude, self.files) & copy_files(folder, self.files)):
                key = f'{name}/{path}'
                if ((claude / path).read_bytes() == (folder / path).read_bytes()
                        and key not in HOST_LINES and key not in UNMATCHED):
                    continue
                found = changed_lines(compared_lines(claude / path), compared_lines(folder / path))
                allowed = allowed_lines(key)
                with self.subTest(file=key):
                    if key in UNMATCHED:
                        self.assertNotEqual(found, allowed, f'the file matches now; remove it from UNMATCHED '
                                                            f'({UNMATCHED[key]})')
                        continue
                    self.assertEqual(
                        sorted(found.elements()), sorted(allowed.elements()),
                        'the copies differ in lines that HOST_LINES does not list (- in the diff below), or '
                        'HOST_LINES lists lines that no longer differ (+ in the diff below). Make the change '
                        'in every copy; list only host-specific lines.')

    def test_allowlist_entries_name_existing_copies(self):
        names = {relative(folder) for hosts in self.copies.values() for folder in hosts.values()}
        host_copies = {name for name, *_ in self.pairs()}
        for key in INVOCATION_EXCEPTIONS:
            with self.subTest(entry=key):
                self.assertTrue(key in names, 'no copy has this folder')
        for key in HOST_FILES:
            with self.subTest(entry=key):
                self.assertTrue(key in host_copies, 'no Codex or Antigravity copy has this folder')
        for key in [*HOST_LINES, *UNMATCHED]:
            with self.subTest(entry=key):
                self.assertTrue('/'.join(key.split('/')[:3]) in host_copies,
                                'no Codex or Antigravity copy has this folder')
                self.assertTrue((ROOT / key).is_file(), 'no file has this path')
        for key, entry in HOST_LINES.items():
            with self.subTest(entry=key):
                self.assertEqual([line for line in entry.splitlines() if line and line[0] not in '-+#'], [],
                                 'start each line with -, +, or #')
                self.assertTrue(allowed_lines(key), 'list at least one - or + line')
        for key, reason in [*UNMATCHED.items(), *INVOCATION_EXCEPTIONS.items()]:
            with self.subTest(entry=key):
                self.assertRegex(reason, r'#\d+', 'name the repair issue')

    def test_frontmatter_follows_the_host_rules(self):
        for package, _, skills in self.registrations:
            for skill in skills:
                fields, _ = split_skill(skill)
                with self.subTest(copy=relative(skill.parent)):
                    self.assertEqual(fields.get('name'), skill.parent.name, 'name the skill as its folder')
                    allowed = ALLOWED_KEYS.get(package.host)
                    if allowed is not None:
                        self.assertLessEqual(set(fields), allowed,
                                             f'{package.host} copies carry only {sorted(allowed)}')
                    if 'disable-model-invocation' in fields:
                        self.assertEqual(fields['disable-model-invocation'], 'true',
                                         'write disable-model-invocation only as true')

    def test_copies_agree_on_the_invocation_policy(self):
        for (plugin, skill), hosts in self.copies.items():
            policy = {relative(folder): user_invoked(host, folder) for host, folder in hosts.items()}
            agreed = {value for name, value in policy.items() if name not in INVOCATION_EXCEPTIONS}
            with self.subTest(skill=f'{plugin}/{skill}', policy=policy):
                self.assertEqual(len(agreed), 1, 'set disable-model-invocation: true in the Claude and Antigravity '
                                                 f'copies and allow_implicit_invocation: false in {CODEX_POLICY} '
                                                 'of the Codex copy, or none of them')
                for name in policy.keys() & INVOCATION_EXCEPTIONS.keys():
                    self.assertNotIn(policy[name], agreed, f'{name} agrees now; remove it from INVOCATION_EXCEPTIONS')

    def test_pinned_skills_keep_their_policy_on_every_host(self):
        found = set()
        for package, _, skills in self.registrations:
            for skill in skills:
                key = (package.source, skill.parent.name)
                if key in PINNED_POLICY and relative(skill.parent) not in INVOCATION_EXCEPTIONS:
                    found.add(key)
                    with self.subTest(copy=relative(skill.parent)):
                        self.assertEqual(user_invoked(package.host, skill.parent), PINNED_POLICY[key][0],
                                         PINNED_POLICY[key][1])
        self.assertEqual(found, set(PINNED_POLICY), 'a pinned skill has no copy')

    def test_copies_name_no_tool_of_another_host(self):
        claude_copies = {skill.parent for package, _, skills in self.registrations if package.host == 'claude'
                         for skill in skills}
        checked = set()
        for package, _, skills in self.registrations:
            for folder in {skill.parent for skill in skills} - claude_copies:
                for path in sorted(copy_files(folder, self.files)):
                    if path.endswith('.md') and package.host in BLOCKED_TERMS:
                        checked.add(package.host)
                        lines = (folder / path).read_text(encoding='utf-8').splitlines()
                        found = [f'line {number}: {term}' for number, line in enumerate(lines, 1)
                                 for term in BLOCKED_TERMS[package.host] if term in line]
                        with self.subTest(file=f'{relative(folder)}/{path}'):
                            self.assertEqual(found, [], f'write the {package.host} tool or a plain verb; see '
                                                        'CONTRIBUTING.md, "Antigravity copies"')
        self.assertEqual(checked, set(BLOCKED_TERMS))


# Each pinned skill keeps its policy on every host: (user-invoked, reason).
PINNED_POLICY = {
    ('productivity-skills', 'gtd-setup'): (True, 'gtd-setup writes global instruction files only because the '
                                                 'user invokes it (#406)'),
    ('dev-skills', 'repo-cleanup'): (False, 'workflows run repo-cleanup after a merge (#247)'),
    ('dev-skills', 'grill-with-research'): (False, 'matt-automode runs grill-with-research as a step (#365)'),
    ('cc-customize', 'claude-prompt-config'): (True, 'claude-prompt-config replaces the global instruction file '
                                                     'only because the user invokes it (#464)'),
}

INVOCATION_EXCEPTIONS = {}

HOST_FILES = {
    # The Codex copy runs a Claude critic with its own scripts.
    'dev-skills/codex-skills/pressure-test': {'-scripts/codex_critic.py', '+scripts/critic_status.py',
                                              '+scripts/limit_call.py'},
    # Antigravity has no plugin agents, so the copy keeps the agent instructions as references.
    'dev-skills/antigravity-skills/project-eval': {'+references/evaluator.md', '+references/verifier.md'},
}

UNMATCHED = {
}

HOST_LINES = {
    'dev-skills/codex-skills/lean-tests/SKILL.md': r'''
# Codex ships no project-eval (#313), so the description does not route to it.
-description: This skill should be used when the user asks to "check the test suite", "audit the tests", "find out why the tests are slow", "make the tests faster", "remove redundant tests", or "review the tests in this change", or asks which pytest tests are flaky, order-dependent, redundant, or check nothing. It measures a Python pytest suite without changing a file and prints a scorecard with one recommended next mode; on request, it makes the suite faster without deleting a test, removes redundant tests under one path with killed-mutant evidence, or reviews the new and changed tests of a change with a weakening gate. To write a test first, use tdd; for bugs in a diff, use /code-review; for a broad evaluation of a project, use project-eval.
+description: This skill should be used when the user asks to "check the test suite", "audit the tests", "find out why the tests are slow", "make the tests faster", "remove redundant tests", or "review the tests in this change", or asks which pytest tests are flaky, order-dependent, redundant, or check nothing. It measures a Python pytest suite without changing a file and prints a scorecard with one recommended next mode; on request, it makes the suite faster without deleting a test, removes redundant tests under one path with killed-mutant evidence, or reviews the new and changed tests of a change with a weakening gate. To write a test first, use tdd; for bugs in a diff, use /code-review.
''',
    'dev-skills/codex-skills/goal-rubric/SKILL.md': r'''
# Each copy renders the /goal condition for its own host by default.
-6. Render the `/goal` condition for the tool that the user names, or for Claude Code when the user names none. Use the framing for that tool in [Condition Framing](#condition-framing).
+6. Render the `/goal` condition for the tool that the user names, or for Codex when the user names none. Use the framing for that tool in [Condition Framing](#condition-framing).
''',
    'dev-skills/antigravity-skills/goal-rubric/SKILL.md': r'''
# Each copy renders the /goal condition for its own host by default.
-6. Render the `/goal` condition for the tool that the user names, or for Claude Code when the user names none. Use the framing for that tool in [Condition Framing](#condition-framing).
+6. Render the `/goal` condition for the tool that the user names, or for Antigravity when the user names none. Use the framing for that tool in [Condition Framing](#condition-framing).
''',
    'dev-skills/codex-skills/grill-with-research/SKILL.md': r'''
-Invoke `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling` with
-the Skill tool, and follow both. If the Skill tool lacks one, resolve its path:
+Follow the `SKILL.md` of `mattpocock-skills:grilling` and
+`mattpocock-skills:domain-modeling`. If the skill list omits one, resolve its
+path. `<plugin-root>` is two levels above this folder:
-python3 "<plugin-root>/scripts/resolve_skill.py" --model-invoked \
+python3 "<plugin-root>/scripts/resolve_skill.py" --host codex --model-invoked \
-- The Skill tool refuses a Matt skill.
''',
    'dev-skills/antigravity-skills/grill-with-research/SKILL.md': r'''
-Invoke `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling` with
-the Skill tool, and follow both. If the Skill tool lacks one, resolve its path:
+Follow `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling`.
+Resolve the path of each `SKILL.md`. `<plugin-root>` is two levels above this
+folder:
-python3 "<plugin-root>/scripts/resolve_skill.py" --model-invoked \
+python3 "<plugin-root>/scripts/resolve_skill.py" --host antigravity --model-invoked \
-- The Skill tool refuses a Matt skill.
-Otherwise, follow the resolved `SKILL.md`.
+Otherwise, read and follow each resolved `SKILL.md`.
''',
    'dev-skills/codex-skills/doc-update/SKILL.md': r'''
# The instruction files that the request can name.
-- If none are specified, scan standard locations: `README.md`, files under `docs/`, top-level `*.md`, and `SKILL.md` / `AGENTS.md` / `CLAUDE.md` (only if the request mentions skills, agents, or Claude configuration). List what was found and confirm scope before editing.
+- If none are specified, scan standard locations: `README.md`, files under `docs/`, top-level `*.md`, and `SKILL.md` / `AGENTS.md` / `CLAUDE.md` (only if the request mentions skills, agents, or Claude Code or Codex configuration). List what was found and confirm scope before editing.
''',
    'dev-skills/antigravity-skills/doc-update/SKILL.md': r'''
-- If none are specified, scan standard locations: `README.md`, files under `docs/`, top-level `*.md`, and `SKILL.md` / `AGENTS.md` / `CLAUDE.md` (only if the request mentions skills, agents, or Claude configuration). List what was found and confirm scope before editing.
+- If none are specified, scan standard locations: `README.md`, files under `docs/`, top-level `*.md`, and `SKILL.md` / `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` (only if the request mentions skills, agents, or Claude Code or Antigravity configuration). List what was found and confirm scope before editing.
# Antigravity reads GEMINI.md as an instruction file.
-Record each **substantive** change in the changelog. If the project documents its changelog place or format, for example in `CONTRIBUTING.md`, `AGENTS.md`, or `CLAUDE.md`, follow it. Otherwise add an entry, newest first, under `## [Unreleased]` in a single central `CHANGELOG.md` at the repository root — or inside `docs/` if that is where documentation lives (create it if missing) — in the format below.
+Record each **substantive** change in the changelog. If the project documents its changelog place or format, for example in `CONTRIBUTING.md`, `GEMINI.md`, `AGENTS.md`, or `CLAUDE.md`, follow it. Otherwise add an entry, newest first, under `## [Unreleased]` in a single central `CHANGELOG.md` at the repository root — or inside `docs/` if that is where documentation lives (create it if missing) — in the format below.
''',
    'dev-skills/codex-skills/matt-automode/SKILL.md': r'''
-In Claude Code, invoke listed skills with the Skill tool. For missing or
-user-invoked skills, resolve their paths and read their `SKILL.md` files:
+In Codex, open listed skills' `SKILL.md` files. Explicit-only skills may be
+omitted from the list; resolve their paths and read them directly:
-python3 "<plugin-root>/scripts/resolve_skill.py" \
+python3 "<plugin-root>/scripts/resolve_skill.py" --host codex \
+`<plugin-root>` is this plugin's root, two levels above the skill folder.
''',
    'dev-skills/antigravity-skills/matt-automode/SKILL.md': r'''
-In Claude Code, invoke listed skills with the Skill tool. For missing or
-user-invoked skills, resolve their paths and read their `SKILL.md` files:
+In Antigravity, resolve the paths of the needed skills, including user-invoked
+skills, then read each `SKILL.md`:
-python3 "<plugin-root>/scripts/resolve_skill.py" \
+python3 "<plugin-root>/scripts/resolve_skill.py" --host antigravity \
+`<plugin-root>` is this plugin's root, two levels above the skill folder.
-Use `dev-skills:step-workflow` for numbered planning files and the session task
-list, within repository layout rules. Keep the planning files in the planning
+Use `dev-skills:step-workflow` for numbered planning files, within repository
+layout rules. Keep the session task list as a Markdown task list in your own
+task artifact, never in a tracked file. Keep the planning files in the planning
-Use the host's PR monitoring mechanism for pending checks.
+For pending PR checks, run `gh pr checks`, and check again later until the
+required checks finish.
-Give each agent a self-contained task, owned files, and relevant planning-file
-sections by path and line. Run each full test suite through
+Start each sub-agent with `invoke_subagent`: `TypeName: "self"`, a `Role`, and a
+`Prompt`. Give each agent a self-contained task, owned files, and relevant
+planning-file sections by path and line. Run each full test suite through
''',
    'dev-skills/codex-skills/pressure-test/SKILL.md': r'''
# In Codex, Codex holds the position, and the critic is Claude, run through Claude Code.
-description: This skill should be used when the user asks to "pressure-test this", "pressure test the plan", "discuss with codex", "debate this with codex", "get codex's take", "deliberate with codex", or wants an independent adversarial review of a design, plan, rubric, PR, failure diagnosis, or decision before concluding, or when another skill needs its decisions reviewed by an independent critic. Claude holds a genuine position while the Codex CLI acts as an always-adversarial read-only critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
+description: This skill should be used when the user asks to "pressure-test this", "pressure test the plan", "discuss with claude", "debate this with claude", "get claude's take", "deliberate with claude", or wants an independent adversarial review of a design, plan, rubric, PR, failure diagnosis, or decision before concluding, or when another skill needs its decisions reviewed by an independent critic. Codex holds a genuine position while the Claude Code CLI runs an always-adversarial read-only Claude critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
-Run a pressure test on a goal: a question, a decision, or a design. You (Claude)
-hold the position. The critic is GPT, run read-only through the Codex CLI in
+Run a pressure test on a goal: a question, a decision, or a design. You (Codex)
+hold the position. The critic is Claude, run read-only through Claude Code in
# The shell function critic, with limit_call.py and critic_status.py, replaces the runner codex_critic.py. A call returns only when it ends (#502).
-runs through the runner script `codex_critic.py`. It sets the read-only flags,
-pins the model, enforces the time limits, and prints one status line.
+runs through the shell function `critic`. It sets the read-only flags,
+pins the model, enforces the time limits, and prints the status line.
-- Time limits: the runner stops a critic call when Codex writes no output for
-  600 seconds (`error:idle`) or when the call has run for 1,800 seconds
-  (`error:timeout`). Both report exit code 124. The preflight smoke call has
-  60 seconds for both limits.
-- Waiting: each call runs in a detached process, so the Bash tool limit does
-  not stop it. A runner command waits for the result for one wait step, then
-  prints `status=running`; then run `wait` (see [Status line](#status-line)).
-  The wait step is 30 seconds less than the Bash tool default timeout,
-  `BASH_DEFAULT_TIMEOUT_MS`: 90 seconds when it is unset, and at most 570
-  seconds. So a runner command prints its status line before the Bash tool
-  moves it to the background, and it needs no Bash tool `timeout`.
-- Critic model: `gpt-6-astra`, the primary model. The user or a calling skill
-  can choose the fallback model, `gpt-6.1-sol`, instead (see
+- Time limits: `limit_call.py` stops a critic call when it has run for
+  `CALL_TIMEOUT`, 1,800 seconds, and exits 124. The preflight smoke call has
+  `SMOKE_TIMEOUT`, 120 seconds.
+- Waiting: a critic command returns only when the call ends. Give each critic
+  command a shell timeout above `CALL_TIMEOUT`, for example 1860000 ms, or
+  poll the command until it exits.
+- Critic model: `claude-opus-5-5`, the primary model. The user or a calling
+  skill can choose the fallback model, `claude-sonnet-5-5`, instead (see
-  runner pins the model on every call, so the skill does not depend on the
-  ambient `~/.codex/config.toml`.
+  `critic` function passes `--model` on every call, and `critic_status.py`
+  accepts a reply only from the current critic model.
# Setup and the critic function set the Claude Code flags; the Codex sandbox can block the claude CLI.
-- Runner settings: the runner sets the reasoning effort, the read-only
-  sandbox, `--disable plugins`, and the working directory `$REPO` on every
-  call. `dev-skills/tests/test_codex_critic.py` checks these values.
-- One goal per critic thread. A new goal starts a new pressure test with its
+- Call settings: setup and the `critic` calls set the reasoning effort, the
+  read-only tools and flags, and the working directory `$REPO` of every call,
+  and turn off the refusal fallback of Claude Code.
+  `dev-skills/tests/test_pressure_test_models.py` checks these calls, and
+  `dev-skills/tests/test_limit_call.py` checks the time limit.
+- Codex sandbox: the `claude` CLI needs network access and write access to
+  `~/.claude`. If the Codex sandbox blocks either, run each `claude` command
+  with escalated permissions. If escalation is unavailable or denied, stop and
+  report that the critic could not run. Write a short conclusion; the ending
+  condition is "critic unavailable".
+- One goal per critic session. A new goal starts a new pressure test with its
# Codex has no Bash tool.
-Each Bash tool call starts a new shell, so variables do not carry over. Setup
+Each command runs in a new shell, so variables do not carry over. Setup
# Setup finds the Codex-only scripts in <skill-dir> and defines the Claude models, the time limits, and critic.
-printed path.
+printed path. `<skill-dir>` is the folder that holds this `SKILL.md`; write
+its absolute path in the block.
-RUNNER="<plugin-root>/skills/pressure-test/scripts/codex_critic.py"
+SKILL_DIR="<skill-dir>"
-  printf 'DIR="%s"\nREPO="%s"\nRUNNER="%s"\n' "$DIR" "$REPO" "$RUNNER"
+  printf 'DIR="%s"\nREPO="%s"\nSKILL_DIR="%s"\n' "$DIR" "$REPO" "$SKILL_DIR"
-PRIMARY_MODEL="gpt-6-astra"
-FALLBACK_MODEL="gpt-6.1-sol"            # when chosen, or after a flag
+PRIMARY_MODEL="claude-opus-5-5"
+FALLBACK_MODEL="claude-sonnet-5-5"      # when chosen, or after a flag
+CALL_TIMEOUT=1800
+SMOKE_TIMEOUT=120
+export CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1
+
+# One read-only critic call. The prompt comes from stdin. limit_call.py stops
+# the call at the time limit and exits 124 only after the CLI has ended. Prints
+# the exit code, the model, and the call time in seconds, then one status from
+# critic_status.py, and writes the reply to $DIR/msg.txt. Appends both lines and
+# the reply to $DIR/replies.md, which keeps every reply. Only the current
+# critic model may answer; any other model is wrong_model.
+critic() {                              # usage: critic <seconds> <effort> [session flags] < prompt
+  local s="$1" effort="$2" start="$SECONDS" rc line verdict; shift 2
+  (cd "$REPO" && python3 "$SKILL_DIR/scripts/limit_call.py" "$s" \
+    claude -p --model "$(cat "$DIR/model")" --effort "$effort" "$@" \
+    --output-format stream-json --verbose --tools "Read,Grep,Glob" \
+    --permission-mode dontAsk --strict-mcp-config --disable-slash-commands \
+    --add-dir "$DIR") > "$DIR/events.jsonl" 2> "$DIR/err.log"
+  rc=$?
+  line="exit=$rc model=$(cat "$DIR/model") seconds=$((SECONDS - start))"
+  verdict="$(python3 "$SKILL_DIR/scripts/critic_status.py" "$DIR/events.jsonl" "$DIR/msg.txt" \
+    "$(cat "$DIR/model")")"
+  printf '%s\n%s\n' "$line" "$verdict"
+  printf '## critic call\n\n%s\n%s\n\n%s\n\n' "$line" "$verdict" "$(cat "$DIR/msg.txt")" >> "$DIR/replies.md"
+}
+
+new_session() { python3 -c 'import uuid; print(uuid.uuid4())' > "$DIR/session_id"; }
-printf '%s\n' "$REPO" > "$DIR/repo"
# The Claude critic has only Read, Grep, and Glob.
-Your sandbox is read-only and has no network, so `gh`, `curl`, a heredoc, and a file write fail. When the packet names a file with line ranges, read those ranges first, for example with `sed -n '120,160p' <file>`, and read the whole file only when the ranges do not settle the point. Long command output is cut short.
+Your only tools are Read, Grep, and Glob, so you cannot run a command or reach the network. When the packet names a file with line ranges, read those ranges first, with the offset and limit of Read, and read the whole file only when the ranges do not settle the point.
# Setup checks the Codex-only scripts.
-test -f "$RUNNER" || echo "runner not found: $RUNNER"
+test -f "$SKILL_DIR/scripts/limit_call.py" || echo "critic scripts not found: $SKILL_DIR/scripts"
# The critic calls, not a runner script, send the prompt.
-The runner sends `prompt.md` followed by `critic.txt` to the critic, so every
+The call blocks send `prompt.md` followed by `critic.txt` to the critic, so every
# The Claude critic models.
-The critic starts on the primary model, `gpt-6-astra`. The user or a calling
-skill can choose the fallback model, `gpt-6.1-sol`, by its ID or a short name,
-for example "pressure-test this with sol". Then run this block once, after
-setup and before the preflight:
+The critic starts on the primary model, `claude-opus-5-5`. The user or a
+calling skill can choose the fallback model, `claude-sonnet-5-5`, by its ID or
+a short name, for example "pressure-test this with sonnet". Then run this
+block once, after setup and before the preflight:
-- A request that names the primary model, for example "astra", needs no
+- A request that names the primary model, for example "opus", needs no
-  critic can use only `gpt-6-astra` or `gpt-6.1-sol`, and ask which one to use.
+  critic can use only `claude-opus-5-5` or `claude-sonnet-5-5`, and ask which
+  one to use.
# The preflight calls claude through critic. The call blocks, so it has no running or busy status.
-A real smoke call catches broken Codex environments that `command -v` cannot
-(failed/missing Codex hooks, auth problems, sandbox refusals).
+A real smoke call catches problems that `command -v` cannot: a missing
+sign-in, a model that the account cannot use, or a sandbox that blocks the
+network.
-python3 "$RUNNER" smoke "$DIR"
+command -v claude  >/dev/null || { echo "claude CLI not found"; exit 1; }
+command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
+printf 'Reply with exactly: ok\n' | critic "$SMOKE_TIMEOUT" low --no-session-persistence
+grep -qiw "ok" "$DIR/msg.txt" && echo "REPLY OK" || { echo "REPLY MISSING"; tail -5 "$DIR/err.log"; }
-- **`status=ok`** — continue to Step 1.
-- **`status=flagged`** — follow [Flags](#flags), then re-run the preflight.
-- **`status=running`** or **`status=error:busy`** — run `wait` as described in
-  [Status line](#status-line), then act on its final status here.
-- **Any other status** — stop. Report a one-line diagnosis from the status line
-  and `$DIR/err.log`, for example "Codex is not signed in", "Codex hooks are
-  failing — check the `~/.codex` plugin cache", or "the critic model is not
+- **`ok` and `REPLY OK`** — continue to Step 1.
+- **`flagged`** — follow [Flags](#flags), then re-run the preflight.
+- **Any other result** — stop. Report a one-line diagnosis from the status line
+  and `$DIR/err.log`, for example "Claude Code is not signed in", "the Codex
+  sandbox blocked network access", or "the critic model is not
# A Codex subagent shares the model family of the main agent, so it is no independent critic.
-  independent critic, so do not continue with self-critique only.
+  independent critic, so do not continue with self-critique only, and do not
+  use a Codex subagent as the critic.
# The kickoff and later rounds call critic with a Claude Code session; test_pressure_test_models.py reads this section (#502).
+## Calling the critic
+
+Kickoff (round 1):
+
-python3 "$RUNNER" kickoff "$DIR" && cat "$DIR/msg.txt"
+new_session
+cat "$DIR/prompt.md" "$DIR/critic.txt" | critic "$CALL_TIMEOUT" xhigh --session-id "$(cat "$DIR/session_id")"
+cat "$DIR/msg.txt"
+```
+
+Later rounds:
+
+```bash
+source "<workdir>/env.sh"
+cat > "$DIR/prompt.md" <<'__PROMPT_END__'
+<pressure-test packet for this round>
+__PROMPT_END__
+cat "$DIR/prompt.md" "$DIR/critic.txt" | critic "$CALL_TIMEOUT" xhigh --resume "$(cat "$DIR/session_id")"
+cat "$DIR/msg.txt"
# The Claude critic has only Read, Grep, and Glob.
-- The critic can read files and run read-only commands in the repository and
-  in `$DIR`. It has no network, so it cannot run `gh` or `curl`. Save issue
+- The critic can read files in the repository and in `$DIR`. It cannot run
+  a command, such as `gh` or `curl`, and it has no network. Save issue
# Claude Code keeps a session, not a thread.
-The critic keeps earlier rounds in its thread. A later packet states the
+The critic keeps earlier rounds in its session. A later packet states the
# Step 6 points to the later-round block.
-6. Otherwise send the next packet:
-
-```bash
-source "<workdir>/env.sh"
-cat > "$DIR/prompt.md" <<'__PROMPT_END__'
-<pressure-test packet for this round>
-__PROMPT_END__
-python3 "$RUNNER" resume "$DIR" && cat "$DIR/msg.txt"
-```
+6. Otherwise send the next packet (see [Calling the critic](#calling-the-critic)).
# critic prints its status line in two lines; critic_status.py reports wrong_model, not running, busy, or no thread id.
-The runner prints `exit=<code> model=<model> seconds=<n> status=<status>`,
-where `seconds` is the time of the call so far. It writes the reply to
-`$DIR/msg.txt`, the Codex events to `$DIR/events.jsonl`, and stderr to
-`$DIR/err.log`. When a call ends, the runner appends its final status line
-and reply to `$DIR/replies.md`, because the next call deletes `msg.txt`. On
-the kickoff, it saves the thread ID to `$DIR/thread_id`; each resume uses
+`critic` prints the status line in two lines. The first line is
+`exit=<code> model=<model> seconds=<n>`, where `seconds` is the time of the
+call; the second line is the status from `critic_status.py`. It writes the
+reply to `$DIR/msg.txt`, the Claude Code events to `$DIR/events.jsonl`, and
+stderr to `$DIR/err.log`. When a call ends, `critic` appends its status line
+and reply to `$DIR/replies.md`, because the next call overwrites `msg.txt`.
+The kickoff saves a new session ID to `$DIR/session_id`; each resume uses
-- **`running`** (exit `-`) — the call continues in its detached process. Wait
-  for it, and repeat until a final status:
-
-  ```bash
-  source "<workdir>/env.sh"
-  python3 "$RUNNER" wait "$DIR" && cat "$DIR/msg.txt"
-  ```
-
-  Run `wait` also when the Bash tool stops a runner command or moves it to the
-  background. The call continues, and `wait` prints its status. Do not start
-  the call again.
-- **`error:busy`** — a call in this work directory still runs, and the runner
-  started no new call. Run `wait` until a final status, then act on that
-  status.
-- **`error:no thread id`** (a kickoff, or a retry that starts a new thread) —
-  the call succeeded but did not emit a `thread.started` event, which means
-  the event shape changed. **STOP** and report the last lines of
-  `$DIR/err.log` and `$DIR/events.jsonl`. Make no retry. The runner never
-  falls back to the `--last` form. Write the conclusion with what exists; the
+- **`wrong_model:<ids>`** — a model other than the current critic model
+  answered. **STOP** and report the model IDs, and do not use the reply.
+  Make no retry. Write the conclusion with what exists; the
-- **`error:timeout`** or **`error:idle`** (exit code 124) — the call reached a
+- **Exit code 124**, with any `error:` status — the call reached a
-- **Any other `error:` status**, for example `error:exit 1` or
-  `error:runner stopped` — the call failed. Follow the **Error** stop
+- **Any other `error:` status**, for example `error:no result event`, or
+  another non-zero exit code — the call failed. Follow the **Error** stop
# A narrow retry of a timed-out kickoff starts a new session; a later round resumes its session.
-The runner reports the time limit only after it has stopped the call, so the
-retry cannot overlap it. Run the retry once; `prompt.md` is unchanged:
+`limit_call.py` exits 124 only after it has stopped the call, so the
+retry cannot overlap it. Run the retry once; `prompt.md` is unchanged.
+
+A timed-out kickoff retries in a new session, because the timed-out call may
+not have created a session that Claude Code can resume:
-python3 "$RUNNER" retry "$DIR" && cat "$DIR/msg.txt"
+new_session
+cat "$DIR/prompt.md" "$DIR/critic.txt" "$DIR/narrow.txt" | critic "$CALL_TIMEOUT" xhigh --session-id "$(cat "$DIR/session_id")"
+cat "$DIR/msg.txt"
-The runner sends `prompt.md`, `critic.txt`, and then `narrow.txt`, with the
-same limits and effort. When the timed-out call saved a thread ID, the retry
-resumes that thread, so the critic keeps what it already read. Otherwise, for
-example when a kickoff stopped before Codex started its thread, the retry
-starts a new thread. Each form follows the status rules of the call it makes.
+A timed-out later round retries in the same session, so the critic keeps what
+it already read:
+
+```bash
+source "<workdir>/env.sh"
+cat "$DIR/prompt.md" "$DIR/critic.txt" "$DIR/narrow.txt" | critic "$CALL_TIMEOUT" xhigh --resume "$(cat "$DIR/session_id")"
+cat "$DIR/msg.txt"
+```
+
+The retry sends `prompt.md`, `critic.txt`, and then `narrow.txt`, with the
+same limit and effort. Each form follows the status rules of the call it makes.
# critic_status.py reports Claude safeguard actions.
-Codex flags a request with a policy error, for example "This request has been
-flagged for possible cybersecurity risk." (`cyber_policy`), a biological-risk
-flag (`bio_policy`), or a misalignment policy error (`misalignment_policy`).
-Codex can also reroute a flagged account to another model. The runner searches
-only error events and stderr for these notices, so the critic's own words
-cannot match, and reports `status=flagged`.
+Any safeguard action flags the call, even when the critic finished its answer.
+`critic_status.py` reports `flagged` when a response ends with
+`stop_reason: "refusal"`, when the result reports `safety_stops` above zero,
+or when Claude Code reports a `model_refusal_fallback` or
+`model_refusal_no_fallback` event.
# The Claude critic models.
-  `gpt-6-astra` is `gpt-6.1-sol`, and the reverse:
+  `claude-opus-5-5` is `claude-sonnet-5-5`, and the reverse:
# Claude Code refuses to reuse a session ID.
-  For the kickoff, the re-run starts a new thread. For a resume, it continues
-  the same thread on the other allowed model. Codex then warns that the
-  session was recorded with the starting model; ignore that warning. Keep the
+  For the kickoff, the re-run calls `new_session` again, because Claude Code
+  refuses to reuse a session ID. For a resume, it continues the same session
+  on the other allowed model. Keep the
# The Error stop uses the statuses of critic_status.py and limit_call.py.
-- **Error** — a runner call reports a final `error:` status without a flag.
-  `error:busy` is not a final status: run `wait`. After `error:no thread id`,
-  make no retry; the ending condition is "cut short". After `error:timeout`
-  or `error:idle`, make one [narrow retry](#narrow-retry); after any other
+- **Error** — a critic call reports an `error:` status, a `wrong_model:`
+  status, or a non-zero exit code, without a flag. After `wrong_model:<ids>`,
+  make no retry; the ending condition is "cut short". After exit code 124,
+  make one [narrow retry](#narrow-retry); after any other
# The progress block names the main agent.
-Claude ▸ <concede/rebut per objection, condensed>
+Codex ▸ <concede/rebut per objection, condensed>
''',
    'dev-skills/antigravity-skills/pressure-test/SKILL.md': r'''
-description: This skill should be used when the user asks to "pressure-test this", "pressure test the plan", "discuss with codex", "debate this with codex", "get codex's take", "deliberate with codex", or wants an independent adversarial review of a design, plan, rubric, PR, failure diagnosis, or decision before concluding, or when another skill needs its decisions reviewed by an independent critic. Claude holds a genuine position while the Codex CLI acts as an always-adversarial read-only critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
+description: This skill should be used when the user asks to "pressure-test this", "pressure test the plan", "discuss with codex", "debate this with codex", "get codex's take", "deliberate with codex", or wants an independent adversarial review of a design, plan, rubric, PR, failure diagnosis, or decision before concluding, or when another skill needs its decisions reviewed by an independent critic. The agent holds a genuine position while the Codex CLI acts as an always-adversarial read-only GPT critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
-Run a pressure test on a goal: a question, a decision, or a design. You (Claude)
-hold the position. The critic is GPT, run read-only through the Codex CLI in
-non-interactive mode. The result is a written conclusion, not code changes.
+Run a pressure test on a goal: a question, a decision, or a design. You hold
+the position. The critic is GPT, run read-only through the Codex CLI in
+non-interactive mode. A critic from another model family shares fewer blind
+spots with you, so a GPT-family agent stops at the
+[cross-family check](#cross-family-check). The result is a written
+conclusion, not code changes.
-- Waiting: each call runs in a detached process, so the Bash tool limit does
-  not stop it. A runner command waits for the result for one wait step, then
-  prints `status=running`; then run `wait` (see [Status line](#status-line)).
-  The wait step is 30 seconds less than the Bash tool default timeout,
-  `BASH_DEFAULT_TIMEOUT_MS`: 90 seconds when it is unset, and at most 570
-  seconds. So a runner command prints its status line before the Bash tool
-  moves it to the background, and it needs no Bash tool `timeout`.
+- Waiting: each call runs in a detached process, so a shell limit does not
+  stop it. A runner command waits for the result for one wait step, 90
+  seconds by default, then prints `status=running`; then run `wait` (see
+  [Status line](#status-line)). A runner command can move to the background
+  after at most 10 seconds. Then wait for its completion message, which gives
+  the exit code and the output. Read the status line in that output before
+  the next step. Do not check the background command in a loop, and do not
+  start the runner command again.
+## Cross-family check
+
+Do this check first, before setup. The critic is GPT. A critic from your own
+model family shares your blind spots, so the pressure test needs an agent
+that does not run a GPT-family model. Antigravity can run a Gemini, Claude,
+or GPT-family model.
+
+- **You run a Gemini, Claude, or other model that is not GPT-family** —
+  continue to setup.
+- **You run a GPT-family model** — stop. Start no critic call, use no
+  same-family critic, and do not continue with self-critique only. Tell the
+  user that no cross-family critic is available, and that this skill needs a
+  Gemini or Claude model. Write a short conclusion; the ending condition is
+  "no cross-family critic".
+
-Each Bash tool call starts a new shell, so variables do not carry over. Setup
+Each command runs in a new shell, so variables do not carry over. Setup
-printed path.
+printed path. `<skill-dir>` is the folder that holds this `SKILL.md`; write
+its absolute path in the block.
-RUNNER="<plugin-root>/skills/pressure-test/scripts/codex_critic.py"
+RUNNER="<skill-dir>/scripts/codex_critic.py"
-  Run `wait` also when the Bash tool stops a runner command or moves it to the
-  background. The call continues, and `wait` prints its status. Do not start
-  the call again.
+  When a runner command moves to the background, wait for its completion
+  message and act on the status line in its output. When the shell stops a
+  runner command before it prints a status line, run `wait`. The call
+  continues, and `wait` prints its status. Do not start the call again.
+- **No cross-family critic** — you run a GPT-family model (see
+  [Cross-family check](#cross-family-check)).
-Claude ▸ <concede/rebut per objection, condensed>
+Agent ▸ <concede/rebut per objection, condensed>
-  or cut short
+  no cross-family critic, or cut short
''',
    'dev-skills/antigravity-skills/project-eval/SKILL.md': r'''
# Antigravity has no /code-review command and starts subagents with invoke_subagent.
-description: This skill should be used when the user asks to "evaluate the project", "run a deep eval", "evaluate the auth module", "evaluate this design doc", "find issues in this feature", or "check the running app for UX issues", or wants a broad evaluation of a feature, a design document or plan, a running web app, or a whole project across code, security, architecture, data and APIs, user experience, frontend design, product, and documentation. It dispatches skeptical evaluator agents, has a separate verifier check every finding, and writes one report. For a diff or PR, use /code-review; for one decision or design choice, use pressure-test.
+description: This skill should be used when the user asks to "evaluate the project", "run a deep eval", "evaluate the auth module", "evaluate this design doc", "find issues in this feature", or "check the running app for UX issues", or wants a broad evaluation of a feature, a design document or plan, a running web app, or a whole project across code, security, architecture, data and APIs, user experience, frontend design, product, and documentation. It starts skeptical evaluator subagents, has a separate verifier subagent check every finding, and writes one report. For a diff or PR, use a code-review skill; for one decision or design choice, use pressure-test.
# Antigravity has no /code-review or /security-review command.
-- **Use instead**: `/code-review` for a diff or PR, `/security-review` for
-  the security of a diff, and `pressure-test` for one decision, design
-  choice, or position.
+- **Use instead**: a code-review skill for a diff or PR, including the
+  security of a diff, and `pressure-test` for one decision, design choice,
+  or position.
# Antigravity reads GEMINI.md.
-   CLAUDE.md or AGENTS.md, the top-level layout, and `git log --oneline -20`.
+   GEMINI.md, AGENTS.md, or CLAUDE.md, the top-level layout, and
+   `git log --oneline -20`.
# Step 3 starts each evaluator with invoke_subagent and its reference file.
-Send one Agent call for each evaluator, all in one message:
+In each prompt, write the absolute path of `<skill-dir>`.
+
+Start each evaluator with `invoke_subagent`:
-Agent(
-  subagent_type: "dev-skills:project-evaluator",
-  description: "Evaluator E<N>: <dimensions>",
-  prompt: "
+invoke_subagent(
+  TypeName: "self",
+  Role: "Evaluator E<N>: <dimensions>",
+  Prompt: "
+    Read <skill-dir>/references/evaluator.md and follow it.
-The evaluators run in the background. Reply to the user and do not wait.
-Do not stop an evaluator unless the user asks.
+`invoke_subagent` returns at once. The evaluators run at the same time as
+you and as each other, and each one sends you a message when it finishes.
+So start every evaluator before you wait, and give each one the `DEADLINE`
+of the run. Do not poll for results. Do not stop an evaluator unless the
+user asks.
# Antigravity has no SendMessage; the agent sends the subagent a message.
-2. If the result has no findings list, or the result is partial (turn
-   limit), resume the evaluator once with SendMessage. Ask for its findings
-   so far in its final-message format, with the stop reason
-   `partial: <reason>`.
+2. If the result has no findings list, or the result is partial, send the
+   evaluator one message. Ask for its findings so far in its final-message
+   format, with the stop reason `partial: <reason>`.
# Step 4 starts each verifier with invoke_subagent and its reference file.
-7. Send one verifier for each batch:
+7. Start one verifier for each batch with `invoke_subagent`:
-   Agent(
-     subagent_type: "dev-skills:finding-verifier",
-     description: "Verify E<N> batch <b>",
-     prompt: "
+   invoke_subagent(
+     TypeName: "self",
+     Role: "Verifier for E<N> batch <b>",
+     Prompt: "
+       Read <skill-dir>/references/verifier.md and follow it.
# Antigravity has no SendMessage; the agent sends the subagent a message.
-3. For missing IDs, resume the verifier once with SendMessage.
-4. If the verifier cannot resume, send one new verifier for the missing IDs
-   only.
+3. For missing IDs, send the verifier one message that asks for their
+   verdicts.
+4. If the verifier cannot answer, start one new verifier for the missing
+   IDs only.
# Antigravity has no plugin agents, so it has no agent tools line to list browser servers in.
-## Browser Servers
-
-Both agents can use the tools of these browser MCP servers: the desktop
-app's browser (`mcp__Claude_Browser__*`), Claude in Chrome
-(`mcp__claude-in-chrome__*`), Chrome DevTools (`mcp__chrome-devtools__*`),
-and Playwright (`mcp__playwright__*`, or
-`mcp__plugin_playwright_playwright__*` from the Playwright plugin). To
-support another server, add its tool prefix to this list and to the
-`tools` line of both agents in the dev-skills plugin: `mcp__<server>__*`
-for a server that the user configured, or
-`mcp__plugin_<plugin>_<server>__*` for a server that a plugin provides.
-
-A tool in the list still needs permission in the session. A server that
-connects after an agent starts gives that agent no tools.
-
''',
    'dev-skills/antigravity-skills/project-eval/references/dimensions.md': r'''
-**Tool tip:** Use WebSearch to check for known CVEs in project dependencies (e.g., search "CVE lodash 4.17.15" or "express 4.18 vulnerabilities"). Code-only analysis catches injection and auth issues, but WebSearch catches known vulnerabilities in third-party packages.
+**Tool tip:** Search the web to check for known CVEs in project dependencies (e.g., search "CVE lodash 4.17.15" or "express 4.18 vulnerabilities"). Code-only analysis catches injection and auth issues, but a web search catches known vulnerabilities in third-party packages.
-**REAL ISSUE (WebSearch-detected):**
+**REAL ISSUE (web-search-detected):**
-Why real: Version 8.5.1 is affected. The call names no `algorithms`, and nothing checks that `JWT_SECRET` is set, so an unset secret makes the server accept a token with no signature. The fix is published: upgrade to 9.0.0 or later and pass `algorithms`. WebSearch found the advisory; code analysis alone would not surface this.
+Why real: Version 8.5.1 is affected. The call names no `algorithms`, and nothing checks that `JWT_SECRET` is set, so an unset secret makes the server accept a token with no signature. The fix is published: upgrade to 9.0.0 or later and pass `algorithms`. A web search found the advisory; code analysis alone would not surface this.
-- `project-rules` — CLAUDE.md compliance, project-specific conventions
+- `project-rules` — Compliance with GEMINI.md, AGENTS.md, or CLAUDE.md, project-specific conventions
''',
    'dev-skills/codex-skills/repo-cleanup/SKILL.md': r'''
# The copy says where <plugin-root> is; the Claude copy uses its plugin-root variable.
-run this command from the checkout that the current session runs in:
+run this command from the checkout that the current session runs in.
+`<plugin-root>` is this plugin's root, two levels above the skill folder.
''',
    'dev-skills/antigravity-skills/repo-cleanup/SKILL.md': r'''
# The copy says where <plugin-root> is; the Claude copy uses its plugin-root variable.
-run this command from the checkout that the current session runs in:
+run this command from the checkout that the current session runs in.
+`<plugin-root>` is this plugin's root, two levels above the skill folder.
''',
    'dev-skills/codex-skills/step-workflow/SKILL.md': r'''
# Codex tracks the steps with update_plan.
-5. **Track the numbered work in the host's task list** - Map each task to its
-   corresponding step, keep at most one task in progress, and leave none in
+5. **Track the numbered work with `update_plan`** - Map each plan item to its
+   corresponding step, keep at most one item in progress, and leave none in
-## Task List Integration
+## Plan Integration
-Each task in the host's task list corresponds to a numbered step:
+Each plan item corresponds to a numbered step:
-Update the task list as the work advances so file order and task state
-remain aligned.
+Use `update_plan` as the work advances so file order and task state remain
+aligned.
''',
    'dev-skills/antigravity-skills/step-workflow/SKILL.md': r'''
# Antigravity has no task-list tool; it keeps a Markdown task list in its task artifact.
-5. **Track the numbered work in the host's task list** - Map each task to its
+5. **Track the numbered work in a Markdown task list** - Keep the list in
+   your own task artifact, never in a tracked file. Map each task to its
-Each task in the host's task list corresponds to a numbered step:
+Each task in the Markdown task list corresponds to a numbered step:
-```text
-1. [in_progress] Load data (01_load_data.py)
-2. [pending] Clean data (02_clean_data.py)
-3. [pending] Run analysis (03_analysis.py)
+```markdown
+- [ ] Load data (01_load_data.py) - in progress
+- [ ] Clean data (02_clean_data.py)
+- [ ] Run analysis (03_analysis.py)
-remain aligned.
+remain aligned. Mark a finished task `[x]`.
''',
    'dev-skills/codex-skills/t3-project-lead/SKILL.md': r'''
+   `<plugin-root>` is two levels above this folder.
''',
    'dev-skills/antigravity-skills/t3-project-lead/SKILL.md': r'''
+   `<plugin-root>` is two levels above this folder.
''',
    'productivity-skills/codex-skills/calendar-manager/SKILL.md': r'''
-Run the Swift source directly (no build step required):
+Run the Swift source directly (no build step required). `<plugin-root>` is the installed plugin directory — the directory that contains `scripts/` and `codex-skills/` (two levels above this skill's folder; in a repository checkout it is `productivity-skills/`). Resolve it to an absolute path and substitute it in every command:
''',
    'productivity-skills/antigravity-skills/calendar-manager/SKILL.md': r'''
-Run the Swift source directly (no build step required):
+Run the Swift source directly (no build step required). `<plugin-root>` is the installed plugin directory — the directory that contains `scripts/` and `antigravity-skills/` (two levels above this skill's folder; in a repository checkout it is `productivity-skills/`). Resolve it to an absolute path and substitute it in every command:
-Before any create/delete operation, list calendars and ask the user which one to use:
+Before any create/delete operation, list calendars and ask the user with `ask_question` which one to use:
''',
    'productivity-skills/codex-skills/gtd-inbox/SKILL.md': r'''
-the intended operation or record is unclear. Use **AskUserQuestion** when
-needed.
+the intended operation or record is unclear. Keep the question concise.
''',
    'productivity-skills/antigravity-skills/gtd-inbox/SKILL.md': r'''
-the intended operation or record is unclear. Use **AskUserQuestion** when
-needed.
+the intended operation or record is unclear. Keep the question concise,
+and use `ask_question` for a choice.
''',
    'productivity-skills/codex-skills/gtd-next/SKILL.md': r'''
-Read the local time and today's native Calendar events. Use the installed plugin root supplied by Claude Code.
+Read the local time and today's native Calendar events. `<plugin-root>` is the installed plugin directory two levels above this skill folder. Resolve it to an absolute path and substitute it below.
''',
    'productivity-skills/antigravity-skills/gtd-next/SKILL.md': r'''
-Read the local time and today's native Calendar events. Use the installed plugin root supplied by Claude Code.
+Read the local time and today's native Calendar events. `<plugin-root>` is the installed plugin directory two levels above this skill folder. Resolve it to an absolute path and substitute it below.
''',
    'productivity-skills/codex-skills/gtd-process/SKILL.md': r'''
-Use **AskUserQuestion** once to approve the inferred batch or give numbered
+Ask the user once to approve the inferred batch or give numbered
''',
    'productivity-skills/antigravity-skills/gtd-process/SKILL.md': r'''
-Use **AskUserQuestion** once to approve the inferred batch or give numbered
+Ask the user once to approve the inferred batch or give numbered
''',
    'productivity-skills/codex-skills/gtd-project/SKILL.md': r'''
-identity is unresolved. Use **AskUserQuestion** when needed. A general
+identity is unresolved. Keep the question concise. A general
''',
    'productivity-skills/antigravity-skills/gtd-project/SKILL.md': r'''
-identity is unresolved. Use **AskUserQuestion** when needed. A general
-review can offer numbered projects and “Done reviewing”.
+identity is unresolved. Keep the question concise, and use `ask_question`
+for a choice. A general review can offer numbered projects and “Done
+reviewing”.
''',
    'productivity-skills/codex-skills/gtd-setup/SKILL.md': r'''
-Ask each question with **AskUserQuestion**. Tool output never confirms a
-step.
+Ask each question concisely and wait for the answer. Tool output never
+confirms a step.
-1. Render the query:
+1. Render the query. `<plugin-root>` is the directory two levels above the
+   directory of this skill:
-   `execute_sql`, and `list_tables`. A host can add a prefix to each name.
+   `execute_sql`, and `list_tables`. A host can add a prefix to each name,
+   for example `mcp__codex_apps__supabase_execute_sql`.
''',
    'productivity-skills/antigravity-skills/gtd-setup/SKILL.md': r'''
-connected route: the host's Supabase connector, which uses the connector's
-sign-in or a personal access token (a token connector).
+connected route: the host's Supabase connector, which in Antigravity is the
+Supabase MCP server that the user connects and signs in to.
-Ask each question with **AskUserQuestion**. Tool output never confirms a
-step.
+Ask each question concisely and wait for the answer. Use `ask_question`
+for a choice. Tool output never confirms a step.
-1. Render the query:
+1. Render the query. `<plugin-root>` is the directory two levels above the
+   directory of this skill:
-2. Discover the host's connected Supabase tools. Tool names differ between
-   hosts. The hosted Supabase server has names such as `list_projects`,
-   `create_project`, `get_cost`, `confirm_cost`, `apply_migration`,
-   `execute_sql`, and `list_tables`. A host can add a prefix to each name.
+2. Discover the connected Supabase tools. The hosted Supabase server has
+   names such as `list_projects`, `create_project`, `get_cost`,
+   `confirm_cost`, `apply_migration`, `execute_sql`, and `list_tables`.
+   A host can add a prefix to each name, so find each tool by the end of
+   its exposed name.
''',
    'pymol-skills/codex-skills/pymol-mcp/SKILL.md': r'''
-Find the tools by their exposed names; Claude Code can add a plugin namespace.
+Find the tools by their exposed names; Codex can add a plugin namespace.
-  MCP client, including a Codex or Antigravity session, then reconnect from
-  Claude Code.
+  MCP client, including a Claude Code session, then reconnect from Codex.
-  that `uv` is available to the local Claude Code process.
+  that `uv` is available to the local Codex process.
''',
    'pymol-skills/antigravity-skills/pymol-mcp/SKILL.md': r'''
-Find the tools by their exposed names; Claude Code can add a plugin namespace.
+Find the tools by their exposed names; Antigravity can add a plugin namespace.
-  MCP client, including a Codex or Antigravity session, then reconnect from
-  Claude Code.
+  MCP client, including a Claude Code or Codex session, then reconnect from
+  Antigravity.
-  that `uv` is available to the local Claude Code process.
+  that `uv` is available to the local Antigravity process.
''',
    'pymol-skills/codex-skills/pymol-setup/SKILL.md': r'''
-description: Set up the PyMOL socket plugin for Claude Code, or diagnose missing PyMOL MCP tools, connection failures, and listener configuration.
+description: Set up the PyMOL socket plugin for Codex, or diagnose missing PyMOL MCP tools, connection failures, and listener configuration.
-# Set up PyMOL for Claude Code
+# Set up PyMOL for Codex
-Use a local Claude Code session on the machine that runs PyMOL. Confirm
-that PyMOL and `uv` are installed. The bundled server uses `uv` to provision
-Python 3.10 or newer and its MCP dependency. The first launch needs access to
-download missing dependencies. The Claude Code process must be able to find
-`uv` on `PATH`.
+Use a local Codex session on the machine that runs PyMOL. Confirm that PyMOL
+and `uv` are installed. The bundled server uses `uv` to provision Python 3.10
+or newer and its MCP dependency. The first launch needs access to download
+missing dependencies. The Codex process must be able to find `uv` on `PATH`.
-Install **PyMOL Skills** from the **cc-toolkit** marketplace if it is
+Install **PyMOL Skills** from the **cc-toolkit** Codex marketplace if it is
-Start a new Claude Code session after installing the package to load its tools.
+Start a new Codex task after installing the package to load its tools.
# Claude Code gives the plugin root as ${CLAUDE_PLUGIN_ROOT}; the other hosts find it from the skill folder.
-Use the installed copy of this plugin, `<plugin-root>`, independent
-of any Codex or Antigravity installation or source checkout.
+The plugin root, `<plugin-root>`, is two levels above the directory that
+holds this `SKILL.md`. Use that installed copy, independent of any Claude
+Code installation or source checkout.
-- Missing tools: check that the Claude Code plugin is installed and
-  enabled, then start a new session.
+- Missing tools: check that the Codex plugin is installed and enabled, then
+  start a new task.
-  and ensure the Claude Code process can find it.
+  and ensure the Codex process can find it.
-- Remote Claude Code session: run the integration locally on the PyMOL
-  machine.
+- Remote Codex host: run the integration locally on the PyMOL machine.
''',
    'pymol-skills/antigravity-skills/pymol-setup/SKILL.md': r'''
-description: Set up the PyMOL socket plugin for Claude Code, or diagnose missing PyMOL MCP tools, connection failures, and listener configuration.
+description: Set up the PyMOL socket plugin for Antigravity, or diagnose missing PyMOL MCP tools, connection failures, and listener configuration.
-# Set up PyMOL for Claude Code
+# Set up PyMOL for Antigravity
-Use a local Claude Code session on the machine that runs PyMOL. Confirm
+Use a local Antigravity conversation on the machine that runs PyMOL. Confirm
-download missing dependencies. The Claude Code process must be able to find
+download missing dependencies. The Antigravity process must be able to find
-Install **PyMOL Skills** from the **cc-toolkit** marketplace if it is
-not installed. See the package [README](../../README.md) for installation.
-Start a new Claude Code session after installing the package to load its tools.
+If **PyMOL Skills** is not installed, run this command, then start a new
+conversation to load its tools:
+
+```bash
+agy plugin install https://github.com/aeghnnsw/cc-toolkit/tree/master/pymol-skills
+```
+
+See the package [README](../../README.md) for installation.
# Claude Code gives the plugin root as ${CLAUDE_PLUGIN_ROOT}; the other hosts find it from the skill folder.
-Use the installed copy of this plugin, `<plugin-root>`, independent
-of any Codex or Antigravity installation or source checkout.
+The plugin root, `<plugin-root>`, is two levels above the directory that
+holds this `SKILL.md`. Use that installed copy, independent of any Claude
+Code or Codex installation or source checkout.
-- Missing tools: check that the Claude Code plugin is installed and
-  enabled, then start a new session.
+- Missing tools: check that `agy plugin list` shows the plugin as enabled,
+  then start a new conversation.
-  and ensure the Claude Code process can find it.
+  and ensure the Antigravity process can find it.
-- Remote Claude Code session: run the integration locally on the PyMOL
-  machine.
+- Remote agent: run the conversation locally on the PyMOL machine.
''',
}


if __name__ == '__main__':
    unittest.main()
