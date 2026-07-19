# Creator Skills and Step Workflow Codex-native Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add native Codex support for `sci-slides`, `sci-figure-format`, and
`step-workflow`, with registry-level proof that Codex loads all three skills
from installed plugin caches.

**Architecture:** Keep the Claude and Codex skill surfaces separate. Add a new
Codex manifest and `codex-skills/` tree to `creator-skills`, extend the existing
`dev-skills/codex-skills/` tree, and advertise only the new plugin through the
repository's Codex marketplace. Validate custom skill roots directly and use an
isolated Codex home plus app-server `skills/list` for native discovery proof.

**Tech Stack:** JSON plugin manifests, Markdown `SKILL.md` files with YAML
frontmatter, `jq`, the skill-creator validator, Python standard library, Codex
CLI/app-server.

## Global Constraints

- Work in `trees/feat-175-codex-creator-skills` on branch
  `feat-175-codex-creator-skills` for issue #175.
- Do not modify either `.claude-plugin/plugin.json` or any file under
  `creator-skills/skills/` or `dev-skills/skills/`.
- Preserve the scientific skill bodies; change only their Codex frontmatter.
- Adapt `step-workflow` only where Codex requires it: trigger wording,
  `update_plan`, and repository-convention precedence.
- Use `creator-skills` version `1.0.1` and bump the Codex `dev-skills` manifest
  from `1.0.0` to `1.0.1`.
- Do not use the bundled generic plugin validator; it rejects the repository's
  supported `./codex-skills/` layout. Use the explicit contract checks below.
- Keep commits, issue text, and any PR text free of AI attribution. Do not add a
  test-plan section to a PR description.

---

### Task 1: Establish failing packaging and behavior baselines

**Files:**

- Inspect: `creator-skills/.codex-plugin/plugin.json`
- Inspect: `creator-skills/codex-skills/`
- Inspect: `dev-skills/codex-skills/step-workflow/SKILL.md`
- Inspect: `.agents/plugins/marketplace.json`

**Interfaces:**

- Consumes: the pre-migration branch state.
- Produces: failing checks and no-skill behavior samples proving the native
  surface is absent.

- [ ] **Step 1: Run the desired-state packaging assertion**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path

root = Path.cwd()
assert (root / "creator-skills/.codex-plugin/plugin.json").is_file()
assert (root / "creator-skills/codex-skills/sci-slides/SKILL.md").is_file()
assert (root / "creator-skills/codex-skills/sci-figure-format/SKILL.md").is_file()
assert (root / "dev-skills/codex-skills/step-workflow/SKILL.md").is_file()

marketplace = json.loads((root / ".agents/plugins/marketplace.json").read_text())
assert sum(plugin["name"] == "creator-skills" for plugin in marketplace["plugins"]) == 1
PY
```

Expected: exits nonzero on the missing creator Codex manifest before checking
the later assertions.

- [ ] **Step 2: Capture no-skill behavior baselines**

Use fresh read-only subagents without loading the source skills. Give them one
scenario each:

1. Review a dense scientific results slide with 11 lines of 18-point text, a
   complex six-panel journal figure, and three unexplained equations.
2. Specify publication formatting for a 10-category Nature single-column
   scientific figure, including size, palette, font, format, resolution, and
   line weight.
3. Organize a new data-analysis feature into sequential scripts, outputs,
   tests, and documentation with explicit file names.

Record which skill-specific rules are absent or inconsistent. These are
content baselines only; Task 3 supplies native loader proof.

---

### Task 2: Add the native plugin and three Codex skills

**Files:**

- Create: `creator-skills/.codex-plugin/plugin.json`
- Create: `creator-skills/codex-skills/sci-slides/SKILL.md`
- Create: `creator-skills/codex-skills/sci-figure-format/SKILL.md`
- Create: `dev-skills/codex-skills/step-workflow/SKILL.md`
- Modify: `dev-skills/.codex-plugin/plugin.json`
- Modify: `.agents/plugins/marketplace.json`

**Interfaces:**

- Consumes: the approved design and existing Claude skill bodies.
- Produces: two installable native plugin versions and three Codex-valid skills.

- [ ] **Step 1: Add the creator Codex manifest**

Create `creator-skills/.codex-plugin/plugin.json`:

```json
{
  "name": "creator-skills",
  "version": "1.0.1",
  "description": "Scientific content creation skills for Codex.",
  "author": {
    "name": "Steven",
    "email": "aeghnnsw@users.noreply.github.com"
  },
  "repository": "https://github.com/aeghnnsw/cc-toolkit",
  "license": "MIT",
  "keywords": [
    "science",
    "scientific",
    "presentation",
    "slides",
    "figures",
    "visualization",
    "publication"
  ],
  "skills": "./codex-skills/",
  "interface": {
    "displayName": "Creator Skills",
    "shortDescription": "Codex-ready scientific slides and figure guidance.",
    "longDescription": "Use Creator Skills to design scientific presentations and format publication-quality scientific figures.",
    "developerName": "Steven",
    "category": "Productivity",
    "capabilities": [
      "Read",
      "Write"
    ],
    "defaultPrompt": [
      "Design an effective scientific presentation.",
      "Review these academic slides.",
      "Format this scientific figure for publication."
    ]
  }
}
```

- [ ] **Step 2: Add the Codex scientific skills**

For `creator-skills/codex-skills/sci-slides/SKILL.md`, preserve the existing
body from `creator-skills/skills/sci-slides/SKILL.md` byte-for-byte after the
closing frontmatter delimiter and use exactly:

```yaml
---
name: sci-slides
description: Use when creating or reviewing scientific presentations, conference talks, lab meetings, journal clubs, or STEM slides involving content density, visual evidence, equations, figures, typography, or cognitive load.
---
```

For `creator-skills/codex-skills/sci-figure-format/SKILL.md`, preserve the
existing body after frontmatter and use exactly:

```yaml
---
name: sci-figure-format
description: Use when creating or reviewing scientific figures for publication, including journal dimensions, resolution, file formats, typography, line weights, colorblind-safe palettes, and Nature, Science, ACS, or RSC requirements.
---
```

- [ ] **Step 3: Add the Codex step workflow**

Create `dev-skills/codex-skills/step-workflow/SKILL.md`. Preserve the numbered
file and sub-step patterns from the Claude skill. Use only `name` and a
`Use when` description in frontmatter. Replace the `TodoWrite` requirement and
section with `update_plan`, and add this precedence rule:

```markdown
1. **Respect repository conventions** - Apply step-based names only when the
   user requests them and they do not conflict with established project layout
```

The remaining workflow rules must keep files together, number them by workflow
order, use underscores, track progress with `update_plan`, and renumber when
needed.

- [ ] **Step 4: Version and advertise the expanded dev plugin**

In `dev-skills/.codex-plugin/plugin.json`:

- change `version` to `1.0.1`;
- add `file-naming` and `organization` keywords;
- mention sequential file organization in `interface.longDescription`;
- append `Organize this feature with numbered step-based file names.` to
  `interface.defaultPrompt`.

Do not change the plugin identity, paths, category, or capabilities.

- [ ] **Step 5: Add creator-skills to the Codex marketplace**

Append this entry after `task-loop` in `.agents/plugins/marketplace.json`:

```json
{
  "name": "creator-skills",
  "source": {
    "source": "local",
    "path": "./creator-skills"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

- [ ] **Step 6: Run fast structural checks**

Run:

```bash
jq . creator-skills/.codex-plugin/plugin.json >/dev/null
jq . dev-skills/.codex-plugin/plugin.json >/dev/null
jq . .agents/plugins/marketplace.json >/dev/null
python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py creator-skills/codex-skills/sci-slides
python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py creator-skills/codex-skills/sci-figure-format
python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py dev-skills/codex-skills/step-workflow
```

Expected: all commands exit `0`.

- [ ] **Step 7: Commit the native package**

```bash
git add .agents/plugins/marketplace.json creator-skills/.codex-plugin creator-skills/codex-skills dev-skills/.codex-plugin/plugin.json dev-skills/codex-skills/step-workflow
git commit -m "Add Codex-native creator and step workflow skills"
```

---

### Task 3: Prove package contracts and native registry loading

**Files:**

- Verify: all Task 2 files
- Verify unchanged: `creator-skills/.claude-plugin/`
- Verify unchanged: `creator-skills/skills/`
- Verify unchanged: `dev-skills/.claude-plugin/`
- Verify unchanged: `dev-skills/skills/`

**Interfaces:**

- Consumes: the completed native package.
- Produces: executable evidence for manifest correctness, installed versions,
  namespaced skill registration, and skill-specific behavior.

- [ ] **Step 1: Run the explicit package contract**

Run a Python standard-library assertion that loads both Codex manifests and the
marketplace, resolves each declared skill root relative to its plugin, proves
the root stays within the plugin, and checks:

- creator root directories equal `sci-figure-format` and `sci-slides`;
- dev root contains `step-workflow`;
- each target folder equals its frontmatter `name`;
- target frontmatter keys equal `name` and `description`;
- creator marketplace count is one with the approved path, policies, and
  category;
- creator version is `1.0.1` and dev version is `1.0.1`;
- no target Codex skill contains `TodoWrite` or a `version:` frontmatter field.

Expected: exits `0` and prints `package contract passed`.

- [ ] **Step 2: Prove the Claude surfaces are unchanged**

Run:

```bash
base=$(git merge-base HEAD master)
git diff --exit-code "$base" -- creator-skills/.claude-plugin creator-skills/skills dev-skills/.claude-plugin dev-skills/skills
```

Expected: no output, exit `0`.

- [ ] **Step 3: Install into an isolated Codex home**

Use Python `tempfile.TemporaryDirectory` and a subprocess environment containing
that directory as `CODEX_HOME`. Within that environment:

1. Run `codex plugin marketplace add <worktree> --json`.
2. Run `codex plugin list --marketplace cc-toolkit --available --json` and
   assert creator `1.0.1` and dev `1.0.1` are discoverable.
3. Run `codex plugin add creator-skills@cc-toolkit --json`.
4. Run `codex plugin add dev-skills@cc-toolkit --json`.

Expected: both installations succeed and the installed metadata reports the
expected versions.

- [ ] **Step 4: Query native `skills/list` in the same isolated home**

Start `codex app-server --stdio` with the Step 3 environment. Send newline-
delimited JSON messages in this order:

```json
{"id":1,"method":"initialize","params":{"clientInfo":{"name":"cc-toolkit-smoke","version":"1.0.0"}}}
{"method":"initialized"}
{"id":2,"method":"skills/list","params":{"cwds":["<absolute-worktree>"],"forceReload":true}}
```

Wait for response `id: 2`, then assert:

- no returned entry contains errors;
- enabled registry names include exactly the target names
  `creator-skills:sci-slides`, `creator-skills:sci-figure-format`, and
  `dev-skills:step-workflow`;
- creator paths contain
  `/creator-skills/1.0.1/codex-skills/<skill>/SKILL.md`;
- the dev path contains
  `/dev-skills/1.0.1/codex-skills/step-workflow/SKILL.md`;
- all three paths are inside the isolated Codex home;
- none resolves under either Claude `skills/` tree.

Terminate the app server in `finally`. Expected: print the three registered
names and exit `0`.

- [ ] **Step 5: Forward-test each skill's behavior**

Use fresh read-only subagents, explicitly loading one new Codex `SKILL.md` per
matching Task 1 scenario. Confirm:

- `sci-slides` supplies its concrete density, typography, figure, and equation
  corrections;
- `sci-figure-format` supplies journal-aware dimensions, palette, font, format,
  resolution, and line-weight guidance;
- `step-workflow` supplies leading-zero step and sub-step names, keeps related
  artifacts together, uses `update_plan`, and respects existing repo
  conventions.

Compare each result with its no-skill baseline. Expected: all skill-specific
requirements are present without Claude-only tool references.

- [ ] **Step 6: Run final repository checks**

Run:

```bash
git diff --check
git status --short
git log --oneline --decorate -3
```

Expected: no whitespace errors; only intentional plan/spec/package changes are
present; the design, pressure-test, plan, and implementation commits are at the
branch tip.
