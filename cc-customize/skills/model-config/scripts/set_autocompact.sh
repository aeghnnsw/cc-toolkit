#!/usr/bin/env bash
# Apply one auto-compact change to the Claude Code user settings file.
#
# Usage: set_autocompact.sh [--file <settings.json>] <action>
#   window <tokens>  set autoCompactWindow, from 100000 to 1000000
#   auto             remove autoCompactWindow, so the window tuned for the model applies
#   off              set autoCompactEnabled to false; /compact keeps working
#   off-all          set env.DISABLE_COMPACT to "1"; this also turns off /compact
#   on               set autoCompactEnabled to true; remove env.DISABLE_AUTO_COMPACT and env.DISABLE_COMPACT
#
# The default file is ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json. Every action also removes
# env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE and env.CLAUDE_CODE_AUTO_COMPACT_WINDOW, so that autoCompactWindow
# is the only threshold in the file (#243, #464). The script keeps every other key, prints each removed key
# with its old value, then the resulting auto-compact keys. It writes through a symlink and keeps the file
# mode. It exits 2 and changes nothing on a usage error, a missing jq, or a file that is not a JSON object.
set -euo pipefail

usage() {
  echo "usage: set_autocompact.sh [--file <settings.json>] window <100000-1000000> | auto | off | off-all | on" >&2
  exit 2
}
fail() {
  echo "error: $1" >&2
  exit 2
}

file="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
if [ "${1:-}" = "--file" ]; then
  [ $# -ge 2 ] || usage
  file="$2"
  shift 2
fi
[ $# -ge 1 ] || usage
action="$1"
shift
window=null
case "$action" in
  window)
    [ $# -eq 1 ] || usage
    case "$1" in
      [1-9][0-9][0-9][0-9][0-9][0-9] | 1000000) window="$1" ;;
      *) fail "the window must be a plain integer from 100000 to 1000000, such as 400000; got '$1'" ;;
    esac
    ;;
  auto | off | off-all | on) [ $# -eq 0 ] || usage ;;
  *) usage ;;
esac
command -v jq >/dev/null 2>&1 || fail "jq is required; install it, for example with 'brew install jq'"

current='{}'
if [ -e "$file" ]; then
  current="$(cat "$file")"
  [ -n "${current//[[:space:]]/}" ] || current='{}'
fi
printf '%s' "$current" | jq -e 'type == "object" and ((.env == null) or (.env | type == "object"))' \
  >/dev/null 2>&1 || fail "$file is not a JSON object with an object env block; no change"

# One expression applies the action and removes the stacked overrides. It returns the new settings and the
# removed env entries.
program='
  (["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "CLAUDE_CODE_AUTO_COMPACT_WINDOW"]
   + if $action == "on" then ["DISABLE_AUTO_COMPACT", "DISABLE_COMPACT"] else [] end) as $drop
  | [(.env // {}) | to_entries[] | select(.key | IN($drop[]))] as $removed
  | if $action == "window" then .autoCompactWindow = $window
    elif $action == "auto" then del(.autoCompactWindow)
    elif $action == "off" then .autoCompactEnabled = false
    elif $action == "off-all" then .env.DISABLE_COMPACT = "1"
    else .autoCompactEnabled = true
    end
  | if .env == null then . else .env |= with_entries(select(.key | IN($drop[]) | not)) end
  | if ($removed | length) > 0 and .env == {} then del(.env) else . end
  | {settings: ., removed: $removed}'
result="$(printf '%s' "$current" | jq --arg action "$action" --argjson window "$window" "$program")"

echo "file: $file"
if printf '%s' "$current" | jq -e --argjson result "$result" '. == $result.settings' >/dev/null; then
  echo "no change"
else
  mkdir -p "$(dirname "$file")"
  printf '%s\n' "$(printf '%s' "$result" | jq '.settings')" >"$file"
fi
printf '%s' "$result" | jq -r '
  (.removed[] | "removed: env.\(.key)=\(.value | tojson)"),
  (.settings | ["autoCompactWindow", "autoCompactEnabled"][] as $key
    | "\($key): \(if has($key) then .[$key] | tojson else "not set" end)"),
  (.settings.env // {} | ["DISABLE_AUTO_COMPACT", "DISABLE_COMPACT"][] as $key
    | "env.\($key): \(if has($key) then .[$key] | tojson else "not set" end)")'
