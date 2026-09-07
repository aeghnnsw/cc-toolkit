#!/usr/bin/env python3
"""Read-only package and release checks for the cc-toolkit marketplace."""
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import tomllib


REGISTRIES = {'claude': '.claude-plugin/marketplace.json', 'codex': '.agents/plugins/marketplace.json'}
NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
CONVENTIONAL_PATHS = {
    'claude': {'skills': 'skills/', 'agents': 'agents/', 'commands': 'commands/', 'hooks': 'hooks/hooks.json'},
    'codex': {'skills': 'skills/'},
}


class InvalidPackage(ValueError):
    """A repository contract cannot be satisfied."""


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    if result.returncode:
        raise InvalidPackage(f'Git {args[0]} failed: {result.stderr.decode(errors="replace").strip()}')
    return result.stdout


def local_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\0' in value:
        raise InvalidPackage(f'expected a local relative path, got {value!r}')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise InvalidPackage(f'path must stay inside its package: {value!r}')
    return path.as_posix()


def require_path(root, relative, owner=None):
    target = root / relative
    owner = root if owner is None else owner
    try:
        if not target.resolve().is_relative_to(owner.resolve()):
            raise InvalidPackage(f'{relative}: path resolves outside its package')
    except RuntimeError as error:
        raise InvalidPackage(f'{relative}: cannot resolve path: {error}') from error
    if not target.exists():
        raise InvalidPackage(f'{relative}: missing required path')
    return target


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidPackage(f'duplicate JSON key {key!r}')
        result[key] = value
    return result


def read_json(root, path, revision=None):
    try:
        text = (git(root, 'show', f'{revision}:{path}').decode() if revision
                else require_path(root, path).read_text())
        value = json.loads(text, object_pairs_hook=unique_object)
        if not isinstance(value, dict):
            raise InvalidPackage('expected a JSON object')
        return value
    except (ValueError, OSError) as error:
        raise InvalidPackage(f'{path}: {error}') from error


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise InvalidPackage(f'invalid plugin version {value!r}; expected major.minor.patch')
    return tuple(map(int, value.split('.')))


@dataclass
class Package:
    name: str
    host: str
    source: str
    manifest_path: str
    manifest: dict


def load_packages(root, revision=None):
    packages = {}
    files = set(git(root, 'ls-tree', '-r', '--name-only', '-z', revision).decode().split('\0')) if revision else None
    for host, path in REGISTRIES.items():
        present = path in files if revision else (root / path).exists()
        if not present:
            continue
        registry = read_json(root, path, revision)
        if not isinstance(registry.get('name'), str) or not registry['name'].strip():
            raise InvalidPackage(f'{path}: missing registry name')
        if not isinstance(registry.get('plugins'), list):
            raise InvalidPackage(f'{path}: plugins must be a list')
        sources = set()
        for entry in registry['plugins']:
            if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) or not NAME.fullmatch(entry['name']):
                raise InvalidPackage(f'{path}: invalid plugin name')
            name = entry['name']
            if (name, host) in packages:
                raise InvalidPackage(f'{path}: duplicate {host} registration {name}')
            source = entry.get('source')
            if host == 'codex':
                if not isinstance(source, dict) or source.get('source') != 'local':
                    raise InvalidPackage(f'{path}: {name} requires a local source')
                source = source.get('path')
            source = local_path(source)
            if source in sources:
                raise InvalidPackage(f'{path}: duplicate source {source}')
            sources.add(source)
            if not revision and not require_path(root, source).is_dir():
                raise InvalidPackage(f'{source}: plugin source must be a directory')
            manifest_path = f'{source}/.{host}-plugin/plugin.json'
            if not revision:
                require_path(root, manifest_path, root / source)
            manifest = read_json(root, manifest_path, revision)
            if manifest.get('name') != name:
                raise InvalidPackage(f'{manifest_path}: identity must match {name}')
            version(manifest.get('version'))
            packages[name, host] = Package(name, host, source, manifest_path, manifest)
    return packages


def declared_paths(package):
    """Paths declared by the host; absent conventional roots remain optional."""
    for field in ('skills', 'agents', 'commands', 'hooks', 'mcpServers'):
        if field not in package.manifest:
            continue
        value = package.manifest[field]
        if isinstance(value, dict) and field in ('hooks', 'mcpServers'):
            continue  # Inline metadata is not a local resource path.
        values = value if isinstance(value, list) else [value]
        if not values:
            raise InvalidPackage(f'{package.manifest_path}: {field} must not be empty')
        for item in values:
            yield field, local_path(item)


def host_paths(package):
    yield from ((field, path, True) for field, path in declared_paths(package))
    for field, path in CONVENTIONAL_PATHS[package.host].items():
        if field not in package.manifest:
            yield field, path.rstrip('/'), False


def discovery_paths(root, package):
    return [(field, path) for field, path, required in host_paths(package)
            if required or (root / package.source / path).exists()]


def validate_skill(path):
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except UnicodeError as error:
        raise InvalidPackage(f'{path}: invalid UTF-8 text') from error
    if not lines or lines[0] != '---' or '---' not in lines[1:]:
        raise InvalidPackage(f'{path}: SKILL.md requires header delimiters')
    fields = {}
    for line in lines[1:lines.index('---', 1)]:
        match = re.match(r'^(name|description):\s*(.*)$', line)
        if match:
            key, value = match.groups()
            if key in fields:
                raise InvalidPackage(f'{path}: duplicate header field {key}')
            fields[key] = value.strip().strip('"\'')
    for key in ('name', 'description'):
        if not fields.get(key) or fields[key] in ('null', '~', '|', '>'):
            raise InvalidPackage(f'{path}: requires nonempty single-line {key}')
    if not NAME.fullmatch(fields['name']):
        raise InvalidPackage(f'{path}: invalid skill name {fields["name"]!r}')


def included_location(root, target, files):
    """Follow aliases through Git entries, not only the final filesystem target."""
    pending = list(target.relative_to(root).parts)
    cursor = root
    links = 0
    while pending:
        cursor = cursor / pending.pop(0)
        if cursor.is_symlink():
            links += 1
            if cursor.relative_to(root).as_posix() not in files or links > 40:
                return False
            destination = Path(os.path.abspath(cursor.parent / os.readlink(cursor)))
            if not destination.is_relative_to(root):
                return False
            pending = list(destination.relative_to(root).parts) + pending
            cursor = root
    relative = cursor.relative_to(root).as_posix()
    return relative in files or any(path.startswith(relative + '/') for path in files)


def require_included(root, target, files):
    for location in (target, target.resolve()):
        if not included_location(root, location, files):
            relative = location.relative_to(root).as_posix()
            raise InvalidPackage(f'{relative}: required resource is not included by Git; add it or correct the path')


def validate_packages(root, packages, files):
    for package in packages.values():
        require_included(root, root / package.manifest_path, files)
        # Check symlinks in Git's inventory, including ones below directory aliases.
        # Ignored local files do not become part of the package during traversal.
        for relative in files:
            if relative.startswith(package.source + '/') and (root / relative).is_symlink():
                target = require_path(root, relative, root / package.source)
                require_included(root, target, files)
        for field, relative in discovery_paths(root, package):
            target = require_path(root, f'{package.source}/{relative}', root / package.source)
            require_included(root, target, files)
            if field in ('skills', 'agents', 'commands') and not target.is_dir():
                raise InvalidPackage(f'{target}: {field} must be a directory')
            if target.suffix == '.json' and target.is_file():
                read_json(root, target.relative_to(root).as_posix())
            if field == 'skills':
                for skill in target.resolve().glob('*/SKILL.md'):
                    if included_location(root, skill, files):
                        require_path(root, skill.relative_to(root).as_posix(), root / package.source)
                        require_included(root, skill, files)
                        validate_skill(skill)


RULES_PATH = 'package-validation.json'


def validate_rules(rules):
    if rules.get('version') != 1 or isinstance(rules.get('version'), bool):
        raise InvalidPackage(f'{RULES_PATH}: expected rules version 1')
    if set(rules) - {'version', 'defaults', 'plugins'}:
        raise InvalidPackage(f'{RULES_PATH}: unknown top-level field')
    defaults = rules.get('defaults', {})
    plugins = rules.get('plugins', {})
    if not isinstance(defaults, dict) or set(defaults) - {'exempt'} or not isinstance(plugins, dict):
        raise InvalidPackage(f'{RULES_PATH}: invalid defaults or plugins')
    for name, rule in [('defaults', defaults), *plugins.items()]:
        if not isinstance(rule, dict) or set(rule) - {'exempt', 'ownership', 'resources'}:
            raise InvalidPackage(f'{RULES_PATH}: invalid rule for {name}')
        exemptions = rule.get('exempt', [])
        if not isinstance(exemptions, list):
            raise InvalidPackage(f'{RULES_PATH}: {name} exemptions must be a list')
        for value in exemptions:
            local_path(value)
        for field in ('ownership', 'resources'):
            entries = rule.get(field, [])
            if not isinstance(entries, list):
                raise InvalidPackage(f'{RULES_PATH}: {name} {field} must be a list')
            seen = set()
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {'path', 'hosts'}:
                    raise InvalidPackage(f'{RULES_PATH}: invalid {name} {field} entry')
                path = local_path(entry['path'])
                if path in seen:
                    raise InvalidPackage(f'{RULES_PATH}: duplicate {name} {field} path {path}')
                seen.add(path)
                hosts = entry['hosts']
                if (not isinstance(hosts, list) or not hosts
                        or any(not isinstance(host, str) or host not in REGISTRIES for host in hosts)
                        or len(set(hosts)) != len(hosts)):
                    raise InvalidPackage(f'{RULES_PATH}: invalid hosts for {name}/{path}')
    return rules


def validate_resources(root, packages, rules, files):
    for package in packages.values():
        for resource in rules.get('plugins', {}).get(package.name, {}).get('resources', []):
            if package.host not in resource['hosts']:
                continue
            relative = f'{package.source}/{local_path(resource["path"])}'
            target = require_path(root, relative, root / package.source)
            require_included(root, target, files)
            if target.suffix == '.toml':
                try:
                    tomllib.loads(target.read_text())
                except ValueError as error:
                    raise InvalidPackage(f'{relative}: invalid TOML: {error}') from error
            elif target.suffix == '.json':
                read_json(root, relative)


def matches(path, pattern):
    normalized = local_path(pattern)
    return path == normalized or (pattern.endswith('/') and path.startswith(normalized + '/'))


def inferred_owners(relative, registrations):
    for host in REGISTRIES:
        if matches(relative, f'.{host}-plugin/'):
            return {host}, 'host manifest'
    owners = set()
    for package in registrations:
        paths = [(field, path + '/' if field in ('skills', 'agents', 'commands') else path)
                 for field, path, _ in host_paths(package)]
        if any(matches(relative, path) for _, path in paths):
            owners.add(package.host)
    return (owners, 'host discovery path') if owners else (None, 'unclassified file; all registered hosts')


def rule_owners(relative, registrations, rules):
    rule = rules.get('plugins', {}).get(registrations[0].name, {})
    for field in ('resources', 'ownership'):
        entries = [entry for entry in rule.get(field, []) if matches(relative, entry['path'])]
        if entries:
            specific = max(entries, key=lambda entry: len(local_path(entry['path'])))
            return set(specific['hosts']), f'explicit {field} rule {specific["path"]}'
    exemptions = rules.get('defaults', {}).get('exempt', []) + rule.get('exempt', [])
    if any(matches(relative, pattern) for pattern in exemptions):
        return set(), 'contributor-only exemption'
    return inferred_owners(relative, registrations)


def affected_paths(package, changed, registrations, rules):
    result = []
    for path in sorted(changed):
        if not path.startswith(package.source + '/'):
            continue
        relative = path[len(package.source) + 1:]
        owners, reason = rule_owners(relative, registrations, rules)
        if owners is None or package.host in owners:
            result.append((path, reason))
    return result


def validate_releases(root, packages, rules, base_ref):
    try:
        base = git(root, 'merge-base', 'HEAD', base_ref).decode().strip()
    except InvalidPackage as error:
        raise InvalidPackage(f'comparison baseline {base_ref!r} unavailable; fetch the target history or select an available --base. {error}') from error
    previous = load_packages(root, base)
    base_files = set(git(root, 'ls-tree', '-r', '--name-only', '-z', base).decode().split('\0'))
    old_rules = validate_rules(read_json(root, RULES_PATH, base)) if RULES_PATH in base_files else rules
    changed = set(git(root, 'diff', '--name-only', '-z', '--no-renames', base, '--').decode().split('\0'))
    changed.update(git(root, 'ls-files', '--others', '--exclude-standard', '-z').decode().split('\0'))
    current_changed = {path for path in changed if path and ((root / path).exists() or (root / path).is_symlink())}
    for key, package in packages.items():
        old = previous.get(key)
        if old is None:
            continue
        current_hosts = [p for p in packages.values() if p.name == package.name]
        old_hosts = [p for p in previous.values() if p.name == package.name]
        affected = affected_paths(package, current_changed, current_hosts, rules) + affected_paths(old, changed & base_files, old_hosts, old_rules)
        if affected and version(package.manifest['version']) <= version(old.manifest['version']):
            raise InvalidPackage(f'{package.name} [{package.host}]: version must increase above {old.manifest["version"]}; changed {affected[0][0]} ({affected[0][1]})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='Target ref used to find the merge base with HEAD')
    args = parser.parse_args()
    start = time.monotonic()
    try:
        root = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip())
        packages = load_packages(root)
        files = set(git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').decode().split('\0')) - {''}
        validate_packages(root, packages, files)
        rules = validate_rules(read_json(root, RULES_PATH))
        validate_resources(root, packages, rules, files)
        validate_releases(root, packages, rules, args.base)
        print(f'PASS: {len(packages)} host registration(s) checked in {time.monotonic() - start:.3f}s')
        return 0
    except (InvalidPackage, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        print(f'Validation completed in {time.monotonic() - start:.3f}s', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
