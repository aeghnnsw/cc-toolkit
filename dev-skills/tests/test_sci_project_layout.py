"""Checks for the sci-project-layout skill.

The paths tests copy the paths.py template into a temporary project, as Set
up does, with the package name `demoproj`. Each check runs Python in a child
process from the project root with src/ on the import path, as `uv run`
would. Git reads only a temporary global config.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOST_SKILLS = {
    "claude": PLUGIN_ROOT / "skills" / "sci-project-layout",
    "codex": PLUGIN_ROOT / "codex-skills" / "sci-project-layout",
}
TEMPLATES = HOST_SKILLS["claude"] / "templates"
KEY = "042-docking-baseline"
VERSION = "processed/kinase-actives/v2"
STEP = f"""\
import sys
from demoproj import paths

inputs = [paths.DATA / "{VERSION}"] + [paths.RESULTS / a for a in sys.argv[1:] if "/" in a]
with paths.new_run("{KEY}", step="02_dock", label="vina-exh16", inputs=inputs) as run:
    (run.dir / "scores.csv").write_text("ligand,score\\n")
    run.info["tools"] = {{"vina": "1.2.5"}}
    run.info["status"] = "set by the step"
    if "--fail" in sys.argv:
        raise RuntimeError("docking failed")
    print(run.dir)
"""


class Project:
    """A temporary git project with the paths template, a step, and one data version."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.root = tmp / "proj"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "DEMOPROJ_"))}
        self.env.update(
            GIT_CONFIG_GLOBAL=str(tmp / "gitconfig"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=str(tmp),
            GIT_AUTHOR_NAME="Test",
            GIT_AUTHOR_EMAIL="test@example.com",
            GIT_COMMITTER_NAME="Test",
            GIT_COMMITTER_EMAIL="test@example.com",
        )
        (tmp / "gitconfig").write_text("")
        install(self.root)
        experiment = self.root / "experiments" / KEY
        experiment.mkdir(parents=True)
        (experiment / "config.yaml").write_text("exhaustiveness: 16\n")
        (experiment / "02_dock.py").write_text(STEP)
        shutil.copyfile(TEMPLATES / "gitignore", self.root / ".gitignore")
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "start")
        (self.root / "data" / VERSION).mkdir(parents=True)

    def git(self, *args: str, cwd: Path | None = None) -> str:
        out = subprocess.run(
            ["git", *args], cwd=cwd or self.root, env=self.env,
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()

    def python(self, *args: str, cwd: Path | None = None, **env: str) -> subprocess.CompletedProcess:
        cwd = cwd or self.root
        return subprocess.run(
            [sys.executable, *args], cwd=cwd, capture_output=True, text=True,
            env={**self.env, "PYTHONPATH": str(cwd / "src"), **env},
        )

    def value(self, name: str, cwd: Path | None = None, **env: str) -> str:
        out = self.python("-c", f"from demoproj import paths; print(paths.{name})", cwd=cwd, **env)
        if out.returncode:
            raise AssertionError(out.stderr)
        return out.stdout.strip()

    def worktree(self) -> Path:
        path = self.root / "trees" / "test-1-wt"
        self.git("worktree", "add", "-q", str(path), "-b", "test-1-wt")
        return path

    def dock(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return self.python(f"experiments/{KEY}/02_dock.py", *args, cwd=cwd)


def install(root: Path) -> None:
    """Copy the template into root/src/demoproj/, as Set up does."""
    package = root / "src" / "demoproj"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    text = (TEMPLATES / "paths.py").read_text()
    (package / "paths.py").write_text(text.replace("myproj", "demoproj").replace("MYPROJ", "DEMOPROJ"))


def run_record(run_dir: Path) -> dict:
    return json.loads((run_dir / "run.json").read_text())


class PathsTemplateTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Project(Path(tmp.name).resolve())

    def test_store_is_the_main_checkout(self) -> None:
        root = self.project.root
        self.assertEqual(self.project.value("STORE"), str(root))
        self.assertEqual(self.project.value("DATA"), str(root / "data"))
        self.assertEqual(self.project.value("RESULTS"), str(root / "results"))
        self.assertEqual(self.project.value("REPO"), str(root))

    def test_worktree_uses_the_main_checkout_store(self) -> None:
        worktree = self.project.worktree()
        self.assertEqual(self.project.value("STORE", cwd=worktree), str(self.project.root))
        self.assertEqual(self.project.value("REPO", cwd=worktree), str(worktree))

    def test_layout_store_set_in_a_worktree_moves_the_store(self) -> None:
        worktree = self.project.worktree()
        store = self.project.tmp / "big-disk" / "store"
        self.project.git("config", "layout.store", str(store), cwd=worktree)
        self.assertEqual(self.project.value("STORE"), str(store))
        self.assertEqual(self.project.value("STORE", cwd=worktree), str(store))

    def test_global_layout_store_is_ignored(self) -> None:
        self.project.git("config", "--global", "layout.store", str(self.project.tmp / "other"))
        self.assertEqual(self.project.value("STORE"), str(self.project.root))

    def test_environment_variable_comes_first(self) -> None:
        self.project.git("config", "layout.store", str(self.project.tmp / "configured"))
        store = self.project.tmp / "node-store"
        self.assertEqual(self.project.value("STORE", DEMOPROJ_STORE=str(store)), str(store))

    def test_relative_store_path_is_refused(self) -> None:
        out = self.project.python("-c", "from demoproj import paths", DEMOPROJ_STORE="store")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("StoreError: DEMOPROJ_STORE must be an absolute path, not: store", out.stderr)
        self.project.git("config", "layout.store", "store")
        out = self.project.python("-c", "from demoproj import paths")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("StoreError: git config layout.store must be an absolute path, not: store", out.stderr)

    def test_outside_git_needs_the_environment_variable(self) -> None:
        copy = self.project.tmp / "copy"
        install(copy)
        out = self.project.python("-c", "from demoproj import paths", cwd=copy)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("StoreError", out.stderr)
        self.assertIn("Set DEMOPROJ_STORE", out.stderr)

    def test_new_run_records_the_run(self) -> None:
        out = self.project.dock("--exhaustiveness", "16")
        self.assertEqual(out.returncode, 0, out.stderr)
        run_dir = Path(out.stdout.strip())
        self.assertEqual(run_dir.parent, self.project.root / "results" / KEY)
        self.assertRegex(run_dir.name, r"^\d{8}-\d{6}_vina-exh16$")
        self.assertEqual((run_dir / "config.yaml").read_text(), "exhaustiveness: 16\n")
        self.assertTrue((run_dir / "scores.csv").is_file())
        record = run_record(run_dir)
        self.assertEqual(record["run_id"], run_dir.name)
        self.assertEqual(record["experiment"], KEY)
        self.assertEqual(record["step"], "02_dock")
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(record["argv"], [f"experiments/{KEY}/02_dock.py", "--exhaustiveness", "16"])
        self.assertEqual(
            record["git"],
            {"sha": self.project.git("rev-parse", "HEAD"), "branch": "main", "dirty": False},
        )
        self.assertEqual(record["inputs"], [f"data/{VERSION}"])
        self.assertEqual(record["tools"], {"vina": "1.2.5"})
        for field in ("started_at", "finished_at"):
            self.assertIsNotNone(datetime.fromisoformat(record[field]).utcoffset())

    def test_run_is_recorded_as_running_until_it_ends(self) -> None:
        code = (
            "import json\nfrom demoproj import paths\n"
            f"with paths.new_run('{KEY}', step='01_prepare') as run:\n"
            "    print(json.loads((run.dir / 'run.json').read_text())['status'])\n"
        )
        out = self.project.python("-c", code)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "running")

    def test_untracked_file_makes_the_run_dirty(self) -> None:
        (self.project.root / "notes.txt").write_text("draft\n")
        out = self.project.dock()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(run_record(Path(out.stdout.strip()))["git"]["dirty"])

    def test_failed_step_marks_the_run_failed(self) -> None:
        out = self.project.dock("--fail")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("RuntimeError: docking failed", out.stderr)
        (run_dir,) = (self.project.root / "results" / KEY).iterdir()
        record = run_record(run_dir)
        self.assertEqual(record["status"], "failed")
        self.assertIsNotNone(record["finished_at"])

    def test_same_second_and_label_gets_a_suffix(self) -> None:
        results = self.project.root / "results" / KEY
        now = time.time()
        for offset in range(4):
            stamp = datetime.fromtimestamp(now + offset).strftime("%Y%m%d-%H%M%S")
            (results / f"{stamp}_vina-exh16").mkdir(parents=True)
        out = self.project.dock()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(Path(out.stdout.strip()).name.endswith("_vina-exh16-2"))

    def test_run_inputs_record_a_chain_that_citation_can_read(self) -> None:
        first = Path(self.project.dock().stdout.strip())
        second = self.project.dock(f"{KEY}/{first.name}")
        self.assertEqual(second.returncode, 0, second.stderr)
        second_dir = Path(second.stdout.strip())
        third = self.project.dock(f"{KEY}/{second_dir.name}")
        self.assertEqual(third.returncode, 0, third.stderr)
        store = self.project.root
        entry = run_record(Path(third.stdout.strip()))["inputs"][1]
        self.assertEqual(entry, f"results/{KEY}/{second_dir.name}")
        seen = []
        while entry:
            record = run_record(store / entry)
            self.assertEqual(record["status"], "succeeded")
            self.assertTrue(record["git"]["sha"])
            self.assertFalse(record["git"]["dirty"])
            seen.append(record["run_id"])
            entry = next((i for i in record["inputs"] if i.startswith("results/")), None)
        self.assertEqual(seen, [second_dir.name, first.name])

    def test_inputs_take_only_version_and_run_folders(self) -> None:
        run_dir = Path(self.project.dock().stdout.strip())
        rejected = {
            "a file in a run": f"paths.RESULTS / '{KEY}/{run_dir.name}/scores.csv'",
            "an experiment's results": f"paths.RESULTS / '{KEY}'",
            "a dataset without a version": "paths.DATA / 'processed/kinase-actives'",
            "a missing version": "paths.DATA / 'processed/kinase-actives/v9'",
            "a tracked file": "paths.REPO / '.gitignore'",
            "a folder outside the store": "paths.REPO / 'experiments'",
        }
        for case, expression in rejected.items():
            with self.subTest(case):
                code = (
                    "from demoproj import paths\n"
                    f"with paths.new_run('{KEY}', step='03_score', inputs=[{expression}]):\n"
                    "    pass\n"
                )
                out = self.project.python("-c", code)
                self.assertNotEqual(out.returncode, 0)
                self.assertIn("ValueError", out.stderr)
                self.assertIn("pinned by the recorded commit", out.stderr)
        self.assertEqual([p.name for p in (self.project.root / "results" / KEY).iterdir()], [run_dir.name])

    def test_inputs_through_a_symlinked_store(self) -> None:
        disk = self.project.tmp / "disk"
        (disk / "data" / VERSION).mkdir(parents=True)
        link = self.project.tmp / "store-link"
        link.symlink_to(disk)
        self.project.git("config", "layout.store", str(link))
        out = self.project.dock()
        self.assertEqual(out.returncode, 0, out.stderr)
        run_dir = Path(out.stdout.strip())
        self.assertEqual(run_dir.parent, link / "results" / KEY)
        self.assertEqual(run_record(run_dir)["inputs"], [f"data/{VERSION}"])

    def test_unknown_experiment_is_refused(self) -> None:
        code = "from demoproj import paths\nwith paths.new_run('999-typo', step='01_x'):\n    pass\n"
        out = self.project.python("-c", code)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("ValueError: No experiment folder", out.stderr)
        self.assertFalse((self.project.root / "results" / "999-typo").exists())

    def test_missing_git_needs_the_environment_variable(self) -> None:
        no_git = self.project.tmp / "empty-path"
        no_git.mkdir()
        out = self.project.python("-c", "from demoproj import paths", PATH=str(no_git))
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("git is not installed. Set DEMOPROJ_STORE", out.stderr)
        store = self.project.tmp / "node-store"
        (store / "data" / VERSION).mkdir(parents=True)
        out = self.project.python(
            f"experiments/{KEY}/02_dock.py", PATH=str(no_git), DEMOPROJ_STORE=str(store)
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(run_record(Path(out.stdout.strip()))["git"], {"sha": None, "branch": None, "dirty": None})

    def test_run_without_git_has_no_commit(self) -> None:
        copy = self.project.tmp / "copy"
        shutil.copytree(self.project.root, copy, ignore=shutil.ignore_patterns(".git"))
        store = self.project.tmp / "node-store"
        (store / "data" / VERSION).mkdir(parents=True)
        out = self.project.python(f"experiments/{KEY}/02_dock.py", cwd=copy, DEMOPROJ_STORE=str(store))
        self.assertEqual(out.returncode, 0, out.stderr)
        record = run_record(Path(out.stdout.strip()))
        self.assertEqual(record["git"], {"sha": None, "branch": None, "dirty": None})


def split_skill(path: Path) -> tuple[dict[str, str], str]:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields, body


def supporting_files(skill_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(skill_dir).as_posix(): path.read_bytes()
        for path in sorted(skill_dir.rglob("*"))
        if path.is_file()
        and path.name != "SKILL.md"
        and not path.name.startswith(".")
        and "__pycache__" not in path.parts
    }


class HostParityTest(unittest.TestCase):
    def test_bodies_match(self) -> None:
        bodies = {host: split_skill(d / "SKILL.md")[1] for host, d in HOST_SKILLS.items()}
        self.assertEqual(bodies["claude"], bodies["codex"])

    def test_frontmatter_differs_only_by_version(self) -> None:
        fields = {host: split_skill(d / "SKILL.md")[0] for host, d in HOST_SKILLS.items()}
        self.assertEqual(fields["codex"]["name"], "sci-project-layout")
        self.assertEqual(set(fields["codex"]), {"name", "description"})
        self.assertEqual({k: v for k, v in fields["claude"].items() if k != "version"}, fields["codex"])

    def test_templates_match(self) -> None:
        claude = supporting_files(HOST_SKILLS["claude"])
        codex = supporting_files(HOST_SKILLS["codex"])
        self.assertEqual(sorted(claude), sorted(codex))
        for name in claude:
            self.assertEqual(claude[name], codex[name], f"{name} differs between hosts")


if __name__ == "__main__":
    unittest.main()
