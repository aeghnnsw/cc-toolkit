#!/usr/bin/env python3
"""Make the planning folder of a task, or list the planning folders.

Usage, in the checkout where the session started:

    python3 dev-skills/scripts/planning_folder.py SLUG [--issue N]
    python3 dev-skills/scripts/planning_folder.py --list

The checkout is the Git working tree that holds the current folder
(`git rev-parse --show-toplevel`). The planning folder is
.scratch/<N>-<SLUG>/ at its top, or .scratch/<YYYYMMDD>-<SLUG>/ with the
local date of today while no issue exists. A slug has lowercase letters,
digits, and hyphens.

1. When `git check-ignore` shows that Git does not ignore .scratch/, the
   script adds /.scratch/ to the file that
   `git rev-parse --path-format=absolute --git-path info/exclude` prints. A
   linked worktree shares that file with the main checkout.
2. The script uses the planning folder when it exists. Otherwise it uses the
   one .scratch/<YYYYMMDD>-<SLUG>/ folder of an earlier day; with --issue, it
   renames that folder to <N>-<SLUG>. Otherwise it creates the folder.
3. It prints the next free step prefix: one more than the greatest numbered
   prefix (NN_) of the folder's entries, with at least two digits, as
   dev-skills:step-workflow names files.

It prints one line for each step, for example:

    Ignore: Git did not ignore .scratch/; added /.scratch/ to /repo/.git/info/exclude
    Planning folder: /repo/.scratch/42-cache-layer (created)
    Next step prefix: 01_

When Git already ignores .scratch/, the Ignore line names the rule as
SOURCE:LINE:PATTERN, from `git check-ignore -v`. The Planning folder line ends with
"(created)", "(exists)", or "(renamed from NAME)".

--list prints the absolute path of each folder in .scratch/ of the checkout,
one for each line, sorted by name. It creates and changes nothing.

t3_project_lead.py and cleanup_plan.py of repo-cleanup import this module
(#599): `init` makes the lead folder with make_folder and ensure_ignored, and
both scripts find the folders with list_folders and entries.

Exit status: 0 on success; 1 when Git fails, when the folder cannot be made,
when .scratch/ has more than one dated folder for the slug, or when Git still
does not ignore .scratch/ after the change; 2 for a usage error. The message
goes to stderr.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys

SCRATCH = ".scratch"
EXCLUDE_LINE = "/.scratch/"
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")
STEP = re.compile(r"(\d+)_")


class Failed(Exception):
    """The script cannot finish; the message names the cause."""


def git(cwd: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in CWD and return the result; a failed command does not raise."""
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        raise Failed("git is not installed") from None


def checkout_top() -> str:
    """Return the top of the Git working tree that holds the current folder."""
    result = git(os.getcwd(), "rev-parse", "--show-toplevel")
    if result.returncode:
        raise Failed(f"not in a Git working tree: {result.stderr.strip()}")
    return result.stdout.strip()


def ignore_rule(top: str) -> str | None:
    """Return the rule that makes Git ignore .scratch/, or None when Git does not ignore it."""
    result = git(top, "check-ignore", "-v", "--", f"{SCRATCH}/")
    if result.returncode == 0:
        return result.stdout.split("\t", 1)[0].strip()  # SOURCE:LINE:PATTERN, without the path
    if result.returncode == 1:
        return None
    raise Failed(f"git check-ignore failed: {result.stderr.strip()}")


def ensure_ignored(top: str) -> str:
    """Make Git ignore .scratch/ and return the Ignore line."""
    rule = ignore_rule(top)
    if rule is not None:
        return f"Ignore: Git ignores {SCRATCH}/ ({rule})"
    result = git(top, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude")
    if result.returncode:
        raise Failed(f"cannot find Git's info/exclude file: {result.stderr.strip()}")
    exclude = result.stdout.strip()
    try:
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "a+", encoding="utf-8") as handle:
            handle.seek(0)
            text = handle.read()
            handle.write(("\n" if text and not text.endswith("\n") else "") + EXCLUDE_LINE + "\n")
    except OSError as error:
        raise Failed(f"cannot add {EXCLUDE_LINE} to {exclude}: {error}") from None
    if ignore_rule(top) is None:
        raise Failed(f"added {EXCLUDE_LINE} to {exclude}, but Git still does not ignore {SCRATCH}/; "
                     f"a .gitignore rule such as !{SCRATCH}/ overrides it")
    return f"Ignore: Git did not ignore {SCRATCH}/; added {EXCLUDE_LINE} to {exclude}"


def dated_folders(scratch: str, slug: str) -> list[str]:
    """Return the names of the .scratch/<YYYYMMDD>-<slug>/ folders."""
    try:
        names = sorted(os.listdir(scratch))
    except FileNotFoundError:
        return []
    except OSError as error:
        raise Failed(f"cannot read {scratch}: {error}") from None
    found = []
    for name in names:
        date, sep, rest = name.partition("-")
        if not (sep and rest == slug and len(date) == 8 and date.isdigit()
                and os.path.isdir(os.path.join(scratch, name))):
            continue
        try:
            datetime.datetime.strptime(date, "%Y%m%d")
        except ValueError:
            continue
        found.append(name)
    return found


def make_folder(top: str, slug: str, issue: int | None) -> tuple[str, str]:
    """Find, rename, or create the planning folder; return its path and what the script did."""
    scratch = os.path.join(top, SCRATCH)
    target = f"{issue}-{slug}" if issue else f"{datetime.date.today():%Y%m%d}-{slug}"
    path = os.path.join(scratch, target)
    if os.path.isdir(path):
        return path, "exists"
    dated = dated_folders(scratch, slug)
    if len(dated) > 1:
        raise Failed(f"{scratch} has more than one folder for {slug}: {', '.join(dated)}; "
                     "move their files into one folder, then run the script again")
    if dated and not issue:
        return os.path.join(scratch, dated[0]), "exists"
    try:
        if dated:
            os.rename(os.path.join(scratch, dated[0]), path)
            return path, f"renamed from {dated[0]}"
        os.makedirs(path)
    except OSError as error:
        raise Failed(f"cannot make the planning folder {path}: {error}") from None
    return path, "created"


def next_step(folder: str) -> str:
    """Return the next free step prefix in FOLDER, such as "03_"."""
    numbers = [match.group(1) for match in map(STEP.match, os.listdir(folder)) if match]
    width = max([2, *map(len, numbers)])
    return f"{max(map(int, numbers), default=0) + 1:0{width}d}_"


def entries(top: str, location: str = SCRATCH) -> list[str]:
    """Return the absolute paths of the entries in LOCATION at TOP, files too, sorted by name.

    A missing LOCATION has no entries. repo-cleanup reads the files too (#599): a file keeps the
    worktree that holds it.
    """
    folder = os.path.join(top, location)
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return []
    except OSError as error:
        raise Failed(f"cannot read {folder}: {error}") from None
    return [os.path.join(folder, name) for name in names]


def list_folders(top: str) -> list[str]:
    """Return the absolute paths of the folders in .scratch/ at TOP, sorted by name."""
    return [path for path in entries(top) if os.path.isdir(path)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slug", nargs="?", help="the task slug, such as cache-layer")
    parser.add_argument("--issue", type=int, metavar="N", help="the issue number of the task")
    parser.add_argument("--list", action="store_true", help="print the planning folders of the checkout")
    args = parser.parse_args(argv[1:])
    if args.list and (args.slug or args.issue is not None):
        parser.error("--list takes no slug and no --issue")
    if not args.list and not args.slug:
        parser.error("give a slug, or --list")
    if args.slug and not SLUG.fullmatch(args.slug):
        parser.error("a slug has lowercase letters, digits, and hyphens, at most 60 characters")
    if args.issue is not None and args.issue < 1:
        parser.error("an issue number is positive")
    try:
        top = checkout_top()
        if args.list:
            for folder in list_folders(top):
                print(folder)
            return 0
        print(ensure_ignored(top), flush=True)
        folder, done = make_folder(top, args.slug, args.issue)
        print(f"Planning folder: {folder} ({done})")
        print(f"Next step prefix: {next_step(folder)}")
    except Failed as error:
        print(f"planning_folder: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
