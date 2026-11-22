"""changed-files: fail on a changed file that a speed or prune run may not change.

Imported by lean_tests.py; never run directly. It classifies each file that
changed from a base ref to a head ref. Continuous integration configuration,
a file outside the project, a file outside --path, and a product file fail.
A test-side file passes, as the gate classifies it, and so do the files of
ALLOWED and DEPENDENCY_NAMES. A file of SECTIONS mixes product data with
test configuration: it passes when each changed section is one of its
allowed sections.
"""

from __future__ import annotations

import fnmatch
import re
from collections import Counter
from pathlib import Path, PurePosixPath

from lt_common import EXAMPLES, UsageError, git, rel
from lt_gate import Project

# Continuous integration: directories at the start of a repository or project path, and file names anywhere.
CI_DIRS = (
    ".github/workflows/", ".github/actions/", ".gitlab/", ".circleci/", ".buildkite/", ".azure-pipelines/",
    ".woodpecker/", "ci/", ".ci/",
)
CI_FILES = frozenset({
    ".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", "azure-pipelines.yaml", "appveyor.yml", ".appveyor.yml",
    "Jenkinsfile", "bitbucket-pipelines.yml", ".drone.yml", ".woodpecker.yml", ".cirrus.yml", "codecov.yml",
    ".codecov.yml", "cloudbuild.yml", "cloudbuild.yaml", "buildspec.yml",
})
# Files that a run may change as a whole, by file name, with the reason.
ALLOWED = {
    **dict.fromkeys(("CLAUDE.md", "AGENTS.md", "GEMINI.md"), "agent instruction file"),
    **dict.fromkeys(("pytest.ini", ".pytest.ini"), "pytest configuration"),
    **dict.fromkeys(("tox.ini", "noxfile.py"), "tox or nox file"),
    **dict.fromkeys(
        ("uv.lock", "poetry.lock", "pdm.lock", "Pipfile.lock", "pylock.toml", "pixi.lock", "conda-lock.yml"),
        "lock file",
    ),
    **dict.fromkeys(("Pipfile", "environment.yml", "environment.yaml"), "dependency file"),
    # speed may set COVERAGE_CORE in a local command that runs coverage.
    **dict.fromkeys(
        ("Makefile", "GNUmakefile", "makefile", "justfile", "Justfile", ".justfile", "Taskfile.yml", "Taskfile.yaml"),
        "task-runner file",
    ),
}
DEPENDENCY_NAMES = ("*requirements*.txt", "*requirements*.in", "*constraints*.txt", "pylock.*.toml")
# The sections that a run may change in a file that also holds product data: the pytest configuration and the
# development dependencies. A section matches when its name is an entry, or starts with an entry and "." or ":".
SECTIONS = {
    "pyproject.toml": (
        "tool.pytest", "dependency-groups", "project.optional-dependencies", "tool.poetry.group",
        "tool.poetry.dev-dependencies", "tool.uv", "tool.pdm.dev-dependencies", "tool.hatch.envs", "tool.tox",
    ),
    "setup.cfg": ("tool:pytest", "options.extras_require", "tox:tox", "testenv"),
}
FAILING = ("ci", "outside-project", "outside-path", "product")


def changed_files_command(args) -> dict:
    directory = Path(args.project).resolve()
    if directory.is_dir() and git(directory, "rev-parse", "--show-toplevel").returncode != 0:
        raise UsageError(f"changed-files needs a Git work tree; {directory} is not in one")
    project = Project(args.project)
    base, head = project.commit(args.base), project.commit(args.head)
    path = scope_path(project, args.path) if args.path else None
    listing = project.git("diff", "--name-status", "-z", "--no-renames", "--no-ext-diff", base, head)
    fields = listing.split("\0")
    files = []
    for status, name in zip(fields[0::2], fields[1::2]):
        kind, detail = classify(project, name, base, head, path)
        inner = project.inner(name)
        shown = inner if inner is not None else rel(project.root / name, project.dir)
        files.append({"path": shown, "status": status[:1], "class": kind, "detail": detail})
    failures = [entry for entry in files if entry["class"] in FAILING]
    return {
        "summary": {
            "passed": not failures,
            "base": base,
            "head": head,
            "path": path,
            "files": len(files),
            "failures": len(failures),
            "counts": dict(sorted(Counter(entry["class"] for entry in files).items())),
            "examples": [entry["path"] for entry in failures[:EXAMPLES]],
        },
        "files": files,
        "failures": failures,
    }


def scope_path(project: Project, path: str) -> str | None:
    """--path relative to the project in POSIX form, or None for the whole project."""
    inner = rel((project.dir / path).resolve(), project.dir)
    if inner == ".." or inner.startswith("../") or PurePosixPath(inner).is_absolute():
        raise UsageError(f"--path {path} is outside the project {project.dir}")
    return None if inner == "." else inner


def classify(project: Project, name: str, base: str, head: str, path: str | None) -> tuple[str, str]:
    """The class of a changed repository path, and the reason for it."""
    inner = project.inner(name)
    for candidate in (name, inner):
        if candidate is not None and (candidate.startswith(CI_DIRS) or PurePosixPath(candidate).name in CI_FILES):
            return "ci", "continuous integration configuration (safety rule 7)"
    if inner is None:
        return "outside-project", "outside the project directory"
    if path is not None and inner != path and not inner.startswith(path + "/"):
        return "outside-path", f"outside {path}"
    if project.is_test_side(inner):
        return "test", "test-side file"
    file = PurePosixPath(inner)
    if file.name in SECTIONS:
        return section_class(project, inner, SECTIONS[file.name], base, head)
    if file.name in ALLOWED:
        return "allowed", ALLOWED[file.name]
    in_requirements = file.parent.name == "requirements" and file.suffix in (".txt", ".in")
    if in_requirements or any(fnmatch.fnmatchcase(file.name, pattern) for pattern in DEPENDENCY_NAMES):
        return "allowed", "dependency file"
    return "product", "not a test-side file"


def section_class(project: Project, path: str, allowed: tuple, base: str, head: str) -> tuple[str, str]:
    """`allowed` when each changed section of a mixed file is an allowed section, else `product`."""
    before = sections(project.text(base, path) or "")
    after = sections(project.text(head, path) or "")
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    if not changed:
        return "allowed", "only comments or blank lines changed"
    blocked = [name for name in changed if not any(
        name == entry or name.startswith((entry + ".", entry + ":")) for entry in allowed
    )]
    shown = ", ".join(f"[{name}]" if name else "the lines before the first section" for name in blocked or changed)
    return ("product" if blocked else "allowed"), f"changed sections: {shown}"


def sections(text: str) -> dict[str, str]:
    """The lines of each section of a TOML or INI file by section name, without blank and comment lines.

    The name "" holds the lines before the first section header.
    """
    found: dict[str, list[str]] = {}
    name = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        header = stripped.split("#", 1)[0].strip()
        if header.startswith("[") and header.endswith("]"):
            name = re.sub(r"\s", "", header.strip("[]"))
        found.setdefault(name, []).append(line.rstrip())
    return {key: "\n".join(lines) for key, lines in found.items()}
