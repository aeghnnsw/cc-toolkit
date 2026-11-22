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
                if (plugin, skill) in PINNED_POLICY:
                    self.assertEqual(agreed, {PINNED_POLICY[plugin, skill][0]}, PINNED_POLICY[plugin, skill][1])

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
}

INVOCATION_EXCEPTIONS = {
    'dev-skills/codex-skills/repo-cleanup': '#453 sets repo-cleanup model-invocable in the Codex copy',
}

HOST_FILES = {
    # The Codex copy runs a Claude critic with its own scripts.
    'dev-skills/codex-skills/pressure-test': {'-scripts/codex_critic.py', '+scripts/critic_status.py',
                                              '+scripts/limit_call.py'},
    # Antigravity has no plugin agents, so the copy keeps the agent instructions as references.
    'dev-skills/antigravity-skills/project-eval': {'+references/evaluator.md', '+references/verifier.md'},
}

UNMATCHED = {
    'dev-skills/codex-skills/doc-update/SKILL.md': '#453: the Codex copy is a separate rewrite',
    'dev-skills/codex-skills/goal-rubric/SKILL.md': '#453: the shared sections drift',
    'dev-skills/antigravity-skills/goal-rubric/SKILL.md': '#453: the shared sections drift',
    'dev-skills/codex-skills/pressure-test/SKILL.md': '#453: the Codex copy drifts beyond its critic changes',
    'dev-skills/antigravity-skills/project-eval/SKILL.md': '#453: the rules and resume steps drift',
    'dev-skills/codex-skills/step-workflow/SKILL.md': '#453: the Claude copy drifts',
    'dev-skills/antigravity-skills/step-workflow/SKILL.md': '#453: the Claude copy drifts',
    'pymol-skills/codex-skills/pymol-mcp/SKILL.md': '#454: the Claude copy predates the Codex rewrite',
    'pymol-skills/antigravity-skills/pymol-mcp/SKILL.md': '#454: the Claude copy predates the Codex rewrite',
    'pymol-skills/codex-skills/pymol-setup/SKILL.md': '#454: the Claude copy predates the Codex rewrite',
    'pymol-skills/antigravity-skills/pymol-setup/SKILL.md': '#454: the Claude copy predates the Codex rewrite',
}

HOST_LINES = {
    'creator-skills/codex-skills/sci-figure-format/SKILL.md': r'''
# Drift, repaired by #466: the descriptions differ.
-description: Guide for creating publication-quality scientific figures that meet major journal standards (Nature, Science, ACS, RSC). Use this skill when users ask about scientific figure formatting, journal requirements, colorblind-safe palettes, resolution/DPI, file formats, fonts, or figure dimensions for publication.
+description: Use when creating or reviewing scientific figures for publication, including journal dimensions, resolution, file formats, typography, line weights, colorblind-safe palettes, and Nature, Science, ACS, or RSC requirements.
''',
    'creator-skills/antigravity-skills/sci-figure-format/SKILL.md': r'''
# Drift, repaired by #466: the descriptions differ.
-description: Guide for creating publication-quality scientific figures that meet major journal standards (Nature, Science, ACS, RSC). Use this skill when users ask about scientific figure formatting, journal requirements, colorblind-safe palettes, resolution/DPI, file formats, fonts, or figure dimensions for publication.
+description: Use when creating or reviewing scientific figures for publication, including journal dimensions, resolution, file formats, typography, line weights, colorblind-safe palettes, and Nature, Science, ACS, or RSC requirements.
''',
    'dev-skills/codex-skills/grill-with-research/SKILL.md': r'''
-Invoke `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling` with
-the Skill tool, and follow both. If the Skill tool lacks one, resolve its path
-and read only the frontmatter:
+Follow the `SKILL.md` of `mattpocock-skills:grilling` and
+`mattpocock-skills:domain-modeling`. If the skill list omits one, resolve its
+path. `<plugin-root>` is two levels above this folder:
-python3 "<plugin-root>/scripts/resolve_skill.py" \
+python3 "<plugin-root>/scripts/resolve_skill.py" --host codex \
-In these cases, stop and report the blocker; use no other workflow:
+Before you open a resolved `SKILL.md`, check its folder. In these cases, stop
+and report the blocker; use no other workflow:
-- The Skill tool refuses a Matt skill.
-- The frontmatter sets `disable-model-invocation: true`.
+- The folder has `agents/openai.yaml` with `allow_implicit_invocation: false`.
-
-Otherwise, follow the resolved `SKILL.md`.
''',
    'dev-skills/antigravity-skills/grill-with-research/SKILL.md': r'''
-Invoke `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling` with
-the Skill tool, and follow both. If the Skill tool lacks one, resolve its path
-and read only the frontmatter:
+Follow `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling`.
+Resolve the path of each `SKILL.md`. `<plugin-root>` is two levels above this
+folder:
-python3 "<plugin-root>/scripts/resolve_skill.py" \
+python3 "<plugin-root>/scripts/resolve_skill.py" --host antigravity \
-In these cases, stop and report the blocker; use no other workflow:
+Read only the frontmatter of each resolved `SKILL.md` first. In these cases,
+stop and report the blocker; use no other workflow:
-- The Skill tool refuses a Matt skill.
-Otherwise, follow the resolved `SKILL.md`.
+Otherwise, read and follow each resolved `SKILL.md`.
''',
    'dev-skills/antigravity-skills/doc-update/SKILL.md': r'''
-- If none are specified, scan standard locations: `README.md`, files under `docs/`, top-level `*.md`, and `SKILL.md` / `AGENTS.md` / `CLAUDE.md` (only if the request mentions skills, agents, or Claude configuration). List what was found and confirm scope before editing.
+- If none are specified, scan standard locations: `README.md`, files under `docs/`, top-level `*.md`, and `SKILL.md` / `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` (only if the request mentions skills, agents, or Claude Code or Antigravity configuration). List what was found and confirm scope before editing.
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
-sections by path and line. Keep plan and task-list tools in this session.
-Allow only one full test suite at a time; other agents can run focused tests.
-State the repository search rules in reviewer briefs, including excluded paths.
-Require measured evidence for claims about external tool behavior.
+Start each sub-agent with `invoke_subagent`: `TypeName: "self"`, a `Role`, and a
+`Prompt`. Give each agent a self-contained task, owned files, and relevant
+planning-file sections by path and line. Keep the task list in this session's
+task artifact. Allow only one full test suite at a time; other agents can run
+focused tests. State the repository search rules in reviewer briefs, including
+excluded paths. Require measured evidence for claims about external tool
+behavior.
''',
    'dev-skills/antigravity-skills/pr-feedback/SKILL.md': r'''
# Only this copy names a review skill; #453 makes both copies name the same one.
-Invoke a code review or PR review skill via the **Skill tool** for the self-review. Do not just run `gh pr diff` and scan it manually — the skill-based review provides structured, thorough analysis that a manual diff scan cannot match.
+Load a code review or PR review skill for the self-review, such as `mattpocock-skills:code-review`. Resolve the path of its `SKILL.md`, then read and follow it. `<plugin-root>` is this plugin's root, two levels above the skill folder:
-If no review skill is available, fall back to a thorough manual review — but always attempt the Skill tool first.
+```bash
+python3 "<plugin-root>/scripts/resolve_skill.py" --host antigravity mattpocock-skills:code-review
+```
+
+Do not just run `gh pr diff` and scan it manually — the skill-based review provides structured, thorough analysis that a manual diff scan cannot match.
+
+If no review skill resolves, fall back to a thorough manual review — but always run the resolver first.
-**Wait via a background-scheduled delay, then read comments:**
+**Wait, then read comments:**
-1. After self-review completes, schedule a 2-minute background wait. Use the Bash tool with `run_in_background: true` and the command `sleep 120`. End your turn after firing — the harness will notify when the wait completes. Do not poll, do not run a foreground `sleep`, do not chain other tool calls in the same turn to check on the wait.
+1. After self-review completes, wait about 2 minutes, then check the PR again.
-2. After the notification, read all reviewer comments on the PR — review summaries, inline review comments, and general PR comments. Extract actionable feedback items.
+2. Read all reviewer comments on the PR — review summaries, inline review comments, and general PR comments. Extract actionable feedback items.
-- Re-invoke review skills via the Skill tool — do not just scan the diff or skim changes
+- Read and follow the review skill's `SKILL.md` again — do not just scan the diff or skim changes
-Ask the user: "PR feedback cycle complete. No new issues found. What would you like to do?"
+Ask the user with `ask_question`: "PR feedback cycle complete. No new issues found. What would you like to do?"
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
-  not stop it. A runner command waits for the result for at most 570 seconds
-  (less when the Bash tool limit is below 600 seconds), then prints
-  `status=running`; then run `wait` (see [Status line](#status-line)). Run
-  every runner command with the Bash tool `timeout` set to `600000`. With the
-  default of 120000 ms, the Bash tool moves a long command to the background
-  after 2 minutes.
+- Waiting: each call runs in a detached process, so a shell limit does not
+  stop it. A runner command waits for the result for at most 570 seconds,
+  then prints `status=running`; then run `wait` (see
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
-  for it with the Bash tool `timeout` set to `600000`, and repeat until a
-  final status:
+  for it, and repeat until a final status:
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
    'dev-skills/antigravity-skills/project-eval/references/dimensions.md': r'''
-**Tool tip:** Use WebSearch to check for known CVEs in project dependencies (e.g., search "CVE lodash 4.17.15" or "express 4.18 vulnerabilities"). Code-only analysis catches injection and auth issues, but WebSearch catches known vulnerabilities in third-party packages.
+**Tool tip:** Search the web to check for known CVEs in project dependencies (e.g., search "CVE lodash 4.17.15" or "express 4.18 vulnerabilities"). Code-only analysis catches injection and auth issues, but a web search catches known vulnerabilities in third-party packages.
-**REAL ISSUE (WebSearch-detected):**
+**REAL ISSUE (web-search-detected):**
-Why real: Known critical vulnerability with a published fix (upgrade to 9.0.0+). WebSearch confirmed the CVE; code analysis alone would not surface this.
+Why real: Known critical vulnerability with a published fix (upgrade to 9.0.0+). A web search confirmed the CVE; code analysis alone would not surface this.
-- `project-rules` — CLAUDE.md compliance, project-specific conventions
+- `project-rules` — Compliance with GEMINI.md, AGENTS.md, or CLAUDE.md, project-specific conventions
''',
    'dev-skills/codex-skills/repo-cleanup/SKILL.md': r'''
# Drift, repaired by #453: the description drops the workflow trigger.
-description: This skill should be used when the user asks to "clean up merged branches", "remove merged worktrees", "run repo-cleanup", or "clean up after the merge", or when a workflow or repository instructions say to run repo-cleanup after work merges. It cleans merged worktrees and branches, reconciles completed issues, deletes their planning folders, and updates the Default Branch.
+description: Clean merged worktrees and branches, reconcile completed issues, delete their planning folders, and update the Default Branch.
-run this command from the checkout that the current session runs in:
+run this command from the checkout that the current session runs in.
+`<plugin-root>` is this plugin's root, two levels above the skill folder.
''',
    'dev-skills/antigravity-skills/repo-cleanup/SKILL.md': r'''
-run this command from the checkout that the current session runs in:
+run this command from the checkout that the current session runs in.
+`<plugin-root>` is this plugin's root, two levels above the skill folder.
+The plan does not read Antigravity transcripts, so it finds another
+Antigravity session only by its process or a Git lock.
+
''',
    'dev-skills/codex-skills/t3-project-lead/SKILL.md': r'''
+   `<plugin-root>` is two levels above this folder.
''',
    'dev-skills/antigravity-skills/t3-project-lead/SKILL.md': r'''
+   `<plugin-root>` is two levels above this folder.
''',
    'productivity-skills/codex-skills/calendar-manager/SKILL.md': r'''
# Drift, repaired by #465: the descriptions differ.
-description: This skill should be used when the user asks to "create calendar event", "add meeting", "schedule appointment", "check calendar", "list upcoming events", "search events", "update event", "delete event", or wants to manage macOS Calendar app events via EventKit CLI. Supports setting event details like title, start/end times, location, and notes. Requires macOS and Calendar.app access permissions.
+description: Use when creating, listing, searching, or deleting macOS Calendar events — scheduling meetings or appointments, checking today's or this week's agenda, or querying date ranges via the bundled EventKit CLI. Requires macOS with Calendar access.
-Run the Swift source directly (no build step required):
+Run the Swift source directly (no build step required). `<plugin-root>` is the installed plugin directory — the directory that contains `scripts/` and `codex-skills/` (two levels above this skill's folder; in a repository checkout it is `productivity-skills/`). Resolve it to an absolute path and substitute it in every command:
''',
    'productivity-skills/antigravity-skills/calendar-manager/SKILL.md': r'''
# Drift, repaired by #465: the descriptions differ.
-description: This skill should be used when the user asks to "create calendar event", "add meeting", "schedule appointment", "check calendar", "list upcoming events", "search events", "update event", "delete event", or wants to manage macOS Calendar app events via EventKit CLI. Supports setting event details like title, start/end times, location, and notes. Requires macOS and Calendar.app access permissions.
+description: Use when creating, listing, searching, or deleting macOS Calendar events — scheduling meetings or appointments, checking today's or this week's agenda, or querying date ranges via the bundled EventKit CLI. Requires macOS with Calendar access.
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
-   authentication, report the required connection or sign-in. For several
-   Claude Code profiles, or for Codex without a connected Supabase app,
-   also name the [token connector](../../references/gtd-token-connector.md).
-   Then stop.
+   authentication, report the required connection or sign-in, give the
+   user these steps, and stop:
+   1. Run `agy mcp add supabase https://mcp.supabase.com/mcp` in a
+      terminal. The command adds the Supabase MCP server to the user's
+      global MCP configuration, `~/.gemini/config/mcp_config.json`. Skip
+      this step when that file already has the server.
+   2. Start a new Antigravity conversation.
+   3. Sign in to Supabase when Antigravity asks.
''',
}


if __name__ == '__main__':
    unittest.main()
