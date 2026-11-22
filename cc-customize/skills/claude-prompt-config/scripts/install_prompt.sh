#!/usr/bin/env bash
# Show, then apply, the replacement of the global Claude Code instruction file with the maintained default.
#
# Usage: install_prompt.sh [--apply] [--asset <file>]
#
# The target is ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md. The new file is the asset, by default
# ../assets/global-claude-md.md next to this script. When the target has a "# GTD agent captures" section
# and the asset has none, the new file keeps that section at its end: gtd-setup step 9 adds it, and without
# it agent captures turn off (#464).
#
# Without --apply, the script writes nothing and prints:
#   target: <path>
#   new file                     the target does not exist
#   unchanged                    the target already has the new content
#   keep: # GTD agent captures   the new file keeps the section of the target
#   drop: <line>                 each line with text that the target has and the new file does not
# With --apply, it also backs up the target to <target>.bak-YYYYMMDD-HHMMSS, writes the new file through a
# symlink, compares the result with the new content, and prints "backup: <path>" and "wrote: <path>".
# It exits 2 and writes nothing on a usage error, a missing asset, or a broken symlink at the target.
set -euo pipefail

usage() {
  echo "usage: install_prompt.sh [--apply] [--asset <file>]" >&2
  exit 2
}
fail() {
  echo "error: $1" >&2
  exit 2
}

asset="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/assets/global-claude-md.md"
apply=0
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --asset) [ $# -ge 2 ] || usage; asset="$2"; shift 2 ;;
    *) usage ;;
  esac
done
[ -f "$asset" ] || fail "no asset at $asset"
dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
target="$dir/CLAUDE.md"
heading='# GTD agent captures'

echo "target: $target"
if [ -L "$target" ] && [ ! -e "$target" ]; then
  fail "$target is a broken symlink; no change"
fi
new="$(mktemp "${TMPDIR:-/tmp}/claude-prompt-config.XXXXXX")"
trap 'rm -f "$new"' EXIT
cat "$asset" >"$new"
if [ -f "$target" ]; then
  if grep -qxF -- "$heading" "$target" && ! grep -qxF -- "$heading" "$asset"; then
    printf '\n' >>"$new"
    awk -v heading="$heading" '$0 == heading { keep = 1; print; next } keep && /^# / { keep = 0 } keep' \
      "$target" >>"$new"
    echo "keep: $heading"
  fi
  if cmp -s "$target" "$new"; then
    echo "unchanged"
    exit 0
  fi
  { diff "$target" "$new" || true; } | sed -n 's/^< //p' | { grep -v '^[[:space:]]*$' || true; } | sed 's/^/drop: /'
else
  echo "new file"
fi
[ "$apply" -eq 1 ] || exit 0

mkdir -p "$dir"
if [ -f "$target" ]; then
  backup="$target.bak-$(date +%Y%m%d-%H%M%S)"
  cp "$target" "$backup"
  echo "backup: $backup"
fi
cat "$new" >"$target"
cmp -s "$target" "$new" || fail "$target does not have the expected content; restore it from the backup"
echo "wrote: $target"
