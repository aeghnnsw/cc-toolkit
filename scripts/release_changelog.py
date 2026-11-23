#!/usr/bin/env python3
"""Release step: move the bullets of each changelog entry file into ## [Unreleased] of CHANGELOG.md, and delete the files.

Run it only in a pull request of its own. The newest entry file comes first; a file keeps the order of its bullets.
"""
import argparse
from pathlib import Path
import sys

import validate_packages as packages


def added_order(root):
    """Return the entry files of HEAD, newest first, by the commit that added each one."""
    log = packages.git(root, 'log', '--format=', '--name-only', '--diff-filter=A', '--', packages.ENTRY_FOLDER)
    return list(dict.fromkeys(line for line in log.decode().splitlines() if line))


def collect(text, additions):
    """Return text with each section's new bullets first in that section of ## [Unreleased]."""
    lines = text.splitlines()
    if '## [Unreleased]' not in lines:
        raise packages.InvalidPackage(f'{packages.CHANGELOG_PATH}: no "## [Unreleased]" heading; add it')
    start = lines.index('## [Unreleased]') + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith('## ')), len(lines))
    block = lines[start:end]
    heads = [index for index, line in enumerate(block) if line.startswith('### ')]
    intro = block[:heads[0]] if heads else block
    sections = [[block[index], block[index + 1:after]] for index, after in zip(heads, heads[1:] + [len(block)])]
    order = packages.CHANGELOG_SECTIONS
    for name in order:
        new = additions.get(name)
        if not new:
            continue
        names = [heading for heading, _ in sections]
        if name in names:
            body = sections[names.index(name)][1]
            rest = body[next((index for index, line in enumerate(body) if line.strip()), len(body)):]
            sections[names.index(name)][1] = ['', *new, *(rest or [''])]
        else:
            # A missing section goes before the first later section, in the order Added, Removed, Changed.
            later = [index for index, heading in enumerate(names)
                     if heading in order and order.index(heading) > order.index(name)]
            sections.insert(later[0] if later else len(sections), [name, ['', *new, '']])
    result = lines[:start] + intro + [line for heading, body in sections for line in (heading, *body)] + lines[end:]
    return '\n'.join(result) + ('\n' if text.endswith('\n') else '')


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        root = Path(packages.git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip())
        folder = root / packages.ENTRY_FOLDER
        paths = sorted(path.relative_to(root).as_posix() for path in folder.iterdir()) if folder.is_dir() else []
        if not paths:
            print(f'No entry files in {packages.ENTRY_FOLDER}/; {packages.CHANGELOG_PATH} is unchanged')
            return 0
        for path in paths:
            if not packages.ENTRY_NAME.fullmatch(path) or not (root / path).is_file():
                raise packages.InvalidPackage(f'{path}: not an entry file; move it out of {packages.ENTRY_FOLDER}/')
        bullets = {path: packages.entry_bullets(path, packages.read_text(root, path)) for path in paths}
        added = added_order(root)
        # A file that no commit added yet is the newest; then the newest commit first.
        paths.sort(key=lambda path: (path in added, added.index(path) if path in added else 0))
        additions = {}
        for path in paths:
            for _, section, line in bullets[path]:
                additions.setdefault(section, []).append(line)
        changelog = root / packages.CHANGELOG_PATH
        if not changelog.is_file():
            raise packages.InvalidPackage(f'{packages.CHANGELOG_PATH}: missing; restore it')
        changelog.write_text(collect(packages.read_text(root, packages.CHANGELOG_PATH), additions), encoding='utf-8')
        for path in paths:
            (root / path).unlink()
        count = sum(len(lines) for lines in additions.values())
        print(f'Moved {count} bullet(s) from {len(paths)} entry file(s) into {packages.CHANGELOG_PATH}, and deleted '
              f'the files: {", ".join(paths)}')
        return 0
    except (packages.InvalidPackage, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
