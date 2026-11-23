#!/usr/bin/env python3
"""Set the next free versions above the target branch for each plugin that the branch changes.

For each affected host, and each host that a new plugin bullet of the branch names, the script sets the manifest
version, and the version of each changed skill that has one, to the next version above the target branch tip. A version that is already above the tip stays. Then it writes
the versions into the plugin bullets of the branch's changelog entry files. A second run changes nothing.
"""
import argparse
from pathlib import Path
import re
import sys

import validate_packages as packages


PARTS = ('major', 'minor', 'patch')
MANIFEST_VERSION = re.compile(r'("version"\s*:\s*")([^"]*)(")')
SKILL_VERSION = re.compile(r'^(version:[ \t]*["\']?)([^"\'\s]+)(["\']?[ \t]*)$', re.MULTILINE)


def raised(value, part):
    major, minor, patch = packages.version(value)
    return {'major': f'{major + 1}.0.0', 'minor': f'{major}.{minor + 1}.0', 'patch': f'{major}.{minor}.{patch + 1}'}[part]


def newest(*values):
    return max((value for value in values if value), key=packages.version)


def replace_one(path, text, pattern, old, new, what):
    """Replace the value old of the one match of pattern in text with new."""
    found = [match for match in pattern.finditer(text) if match[2] == old]
    if len(found) != 1:
        raise packages.InvalidPackage(f'{path}: found {len(found)} {what} lines with {old}; expected 1. '
                                      f'Set {new} by hand')
    return text[:found[0].start(2)] + new + text[found[0].end(2):]


def set_skill_version(path, text, old, new):
    lines = text.splitlines(keepends=True)
    end = next(index for index, line in enumerate(lines[1:], 1) if line.rstrip('\r\n') == '---')
    header = replace_one(path, ''.join(lines[:end]), SKILL_VERSION, old, new, 'frontmatter version')
    return header + ''.join(lines[end:])


def host_text(versions):
    """Write [(host, version)] in the entry form: 'Claude Code and Codex 1.2.0, Antigravity 1.0.1'."""
    groups = []
    for host, value in versions:
        if groups and groups[-1][1] == value:
            groups[-1][0].append(packages.HOST_LABELS[host])
        else:
            groups.append(([packages.HOST_LABELS[host]], value))
    names = [labels[0] if len(labels) == 1 else ' and '.join(labels) if len(labels) == 2
             else ', '.join(labels[:-1]) + ', and ' + labels[-1] for labels, _ in groups]
    return ', '.join(f'{name} {value}' for name, (_, value) in zip(names, groups))


def branch_bullets(root, changes):
    """Return {entry file: (its text, the lines that it had at the merge base)} for the branch's entry files."""
    folder = packages.ENTRY_FOLDER + '/'
    return {path: (packages.read_text(root, path),
                   set(packages.read_text(root, path, changes.base).splitlines())
                   if path in changes.base_files else set())
            for path in sorted(changes.current) if path.startswith(folder)}


def named_hosts(entries):
    """Map each plugin that a new bullet of the branch names to the hosts that the bullet names."""
    named = {}
    for text, earlier in entries.values():
        for line in text.splitlines():
            match = packages.CHANGELOG_BULLET.fullmatch(line)
            if match and match['plugin'] and line not in earlier:
                hosts = packages.changelog_hosts(match['hosts']) or []
                named.setdefault(match['plugin'], set()).update(host for host, _ in hosts)
    return named


def plan(root, base_ref, part):
    """Return ({path: new text}, [report line]) without writing a file."""
    now = packages.load_packages(root)
    files = set(packages.git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
                .decode().split('\0')) - {''}
    rules = packages.validate_rules(packages.read_json(root, packages.RULES_PATH))
    changes = packages.branch_changes(root, rules, base_ref)
    tip = packages.git(root, 'rev-parse', '--verify', f'{base_ref}^{{commit}}').decode().strip()
    tip_files = set(packages.git(root, 'ls-tree', '-r', '--name-only', '-z', tip).decode().split('\0'))
    previous = packages.load_packages(root, changes.base)
    latest = packages.load_packages(root, tip)
    entries = branch_bullets(root, changes)
    # A host that a bullet of the branch names also keeps its increase, for example after a change only to
    # tests, so that the bullet stays true after a rebase.
    named = named_hosts(entries)
    writes, report, skills = {}, [], {}
    for key, package in sorted(now.items()):
        old = previous.get(key)
        if old is None:
            continue  # A new registration needs no increase.
        affected = packages.package_changes(package, old, now, previous, rules, changes)
        if not affected and package.host not in named.get(package.name, ()):
            continue
        floor = newest(old.manifest['version'], latest[key].manifest['version'] if key in latest else None)
        value = package.manifest['version']
        if packages.version(value) <= packages.version(floor):
            new = raised(floor, part)
            text = writes.get(package.manifest_path) or packages.read_text(root, package.manifest_path)
            writes[package.manifest_path] = replace_one(package.manifest_path, text, MANIFEST_VERSION, value, new,
                                                        '"version"')
            package.manifest['version'] = new
            report.append(f'{package.name} [{package.host}]: {value} -> {new} in {package.manifest_path}')
        tip_skills = packages.skill_files(latest[key], tip_files) if key in latest else {}
        for name, path, former, _ in packages.changed_skills(root, package, old, files, changes, affected):
            if path in skills:
                continue  # A skill folder that two hosts share.
            old_value = packages.skill_version(root, former, changes.base)
            if not old_value:
                continue  # A skill without a base version needs no increase.
            value = packages.skill_version(root, path)
            if not value:
                raise packages.InvalidPackage(f'{path}: skill {name} lost its version line; restore it, then run '
                                              'the script again')
            tip_value = packages.skill_version(root, tip_skills[name], tip) if name in tip_skills else None
            floor = newest(old_value, tip_value)
            if packages.version(value, path) <= packages.version(floor):
                new = raised(floor, part)
                writes[path] = set_skill_version(path, packages.read_text(root, path), value, new)
                skills[path] = (name, new)
                report.append(f'{package.name} skill {name}: {value} -> {new} in {path}')
    risen = packages.risen_hosts(now, previous)
    for path, (text, earlier) in entries.items():
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            body = line.rstrip('\r\n')
            match = packages.CHANGELOG_BULLET.fullmatch(body)
            if not match or match['plugin'] not in risen or body in earlier:
                continue  # A bullet that the file had at the merge base belongs to an earlier change.
            hosts = [(host, now[match['plugin'], host].manifest['version'])
                     for host in packages.HOSTS if host in risen[match['plugin']]]
            new = body[:match.start('hosts')] + host_text(hosts) + body[match.end('hosts'):]
            for name, value in skills.values():
                # Any version of the skill: the bullet can hold the version of either side of a conflict.
                new = re.sub(rf'(?<![\w-]){re.escape(name)} \d+\.\d+\.\d+(?!\.?\d)', f'{name} {value}', new)
            if new != body:
                lines[index] = new + line[len(body):]
                report.append(f'{path}:{index + 1}: {match["plugin"]} ({match["hosts"]}) -> ({host_text(hosts)})')
        if ''.join(lines) != text:
            writes[path] = ''.join(lines)
    return writes, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='Target ref, such as origin/master; fetch it first')
    parser.add_argument('--part', choices=PARTS, default='minor',
                        help='Version part to raise above the target: minor (default), patch for a fix, or major')
    args = parser.parse_args()
    try:
        root = Path(packages.git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip())
        writes, report = plan(root, args.base, args.part)
        for path, text in writes.items():
            (root / path).write_text(text, encoding='utf-8')
        print('\n'.join(report) if report else f'No change: each changed plugin and skill is above {args.base}')
        print(f'Next: uv run --no-project --python \'>=3.11\' python scripts/validate_packages.py --base {args.base}')
        return 0
    except (packages.InvalidPackage, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
