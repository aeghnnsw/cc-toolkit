#!/usr/bin/env bash
# Standalone Claude Code statusline.
# Claude Code cancels a statusline run that is still busy when the next update
# arrives, so keep this fast: one jq call, bash math only, cached git status,
# and the session token total is updated in a detached background process.

INPUT=$(cat)
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CONFIG_DIR/settings.json"
[ -f "$SETTINGS" ] || SETTINGS=/dev/null

# Parse every field in one jq call into shell variables. Numeric fields are
# digits or empty, so they are safe in bash arithmetic. Invalid settings JSON
# is ignored.
eval "$(printf '%s' "$INPUT" | jq -r --rawfile s "$SETTINGS" '
  def n: if . == null then "" else tostring end;
  def num: if type == "number" then floor | tostring else "" end;
  ((try ($s | fromjson) catch null) // {}) as $set
  | {
    MODEL:      (.model.display_name // .model.id // "Claude"),
    SESSION:    (.session_id // "x"),
    SESS_NAME:  (.session_name | n),
    TRANSCRIPT: (.transcript_path | n),
    CWD:        (.workspace.current_dir // .cwd // ""),
    EFFORT:     (.effort.level | n),
    FAST:       (.fast_mode | n),
    THINKING:   (.thinking.enabled | n),
    VIM:        (.vim.mode | n),
    WT_NAME:    (.worktree.name // .workspace.git_worktree | n),
    PR_NUM:     (.pr.number | n),
    PR_STATE:   (.pr.review_state | n),
    CTX_SIZE:   (.context_window.context_window_size | num),
    CTX_IN:     (.context_window.total_input_tokens | num),
    ACW:        ($set.autoCompactWindow | num),
    AC_ON:      ($set.autoCompactEnabled | n),
    COST:       (.cost.total_cost_usd // 0 | . * 100 | round | num),
    RL5:        (.rate_limits.five_hour.used_percentage | num),
    RL5_AT:     (.rate_limits.five_hour.resets_at | num),
    RL7:        (.rate_limits.seven_day.used_percentage | num),
    RL7_AT:     (.rate_limits.seven_day.resets_at | num),
    SPEND:      (.rate_limits.spend_limit.used_percentage | num),
    PC_WARM:    (.prompt_cache.warm | n),
    PC_TTL:     (.prompt_cache.ttl | n),
    PC_EXP:     (.prompt_cache.expires_at | num),
    PC_HIT:     (.prompt_cache.hit_ratio | if type == "number" then . * 100 | num else "" end),
    PC_MISS:    (.prompt_cache.misses | num)
  } | to_entries[] | "\(.key)=\(.value | @sh)"
' 2>/dev/null)"

NOW=$(date +%s)
DIM=$'\033[2m'; RST=$'\033[0m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; CYAN=$'\033[36m'
SEP=" ${DIM}│${RST} "

# File mtime in epoch seconds (GNU stat, then BSD/macOS stat).
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0; }

# Per-session state in a private directory. When the directory is not ours
# (another user created it first), run without state.
umask 077
STATE=""
ROOT="${TMPDIR:-/tmp}/cc-statusline-$(id -u)"
mkdir -p "$ROOT" 2>/dev/null
if [ -d "$ROOT" ] && [ ! -L "$ROOT" ] && [ -O "$ROOT" ] && chmod 700 "$ROOT" 2>/dev/null; then
  STATE="$ROOT/${SESSION//[^A-Za-z0-9_-]/_}"
  mkdir -p "$STATE/files" 2>/dev/null || STATE=""
fi
[ -n "$STATE" ] && printf '%s' "$INPUT" > "$STATE/last-input.json" 2>/dev/null   # for debugging

# 10-char bar, colored by percentage.
make_bar() {
  local pct=${1:-0} filled i bar="" color=$GREEN
  (( pct > 100 )) && pct=100
  filled=$(( pct / 10 ))
  for ((i=0; i<filled; i++)); do bar+="█"; done
  for ((i=filled; i<10; i++)); do bar+="░"; done
  if (( pct >= 90 )); then color=$RED; elif (( pct >= 50 )); then color=$YELLOW; fi
  printf '%s%s%s' "$color" "$bar" "$RST"
}

# 1234 -> 1.2K, 1234567 -> 1.2M
fmt_k() {
  local n=${1:-0}
  if (( n >= 1000000 )); then printf '%d.%dM' $((n/1000000)) $((n%1000000/100000))
  elif (( n >= 1000 )); then printf '%d.%dK' $((n/1000)) $((n%1000/100))
  else printf '%d' "$n"; fi
}

# Seconds -> "2d 3h", "1h 5m", "12m"
fmt_dur() {
  local s=${1:-0}
  (( s < 0 )) && s=0
  if (( s >= 86400 )); then printf '%dd %dh' $((s/86400)) $((s%86400/3600))
  elif (( s >= 3600 )); then printf '%dh %dm' $((s/3600)) $((s%3600/60))
  else printf '%dm' $((s/60)); fi
}

# Sum token usage (input + cache write + cache read + output) of the main
# transcript and its subagent transcripts. Reads only bytes added since the
# last run; a message is split over several lines with the same id, so count
# each id once.
update_tokens() {
  local tp=$1 dir=$2 f key off last i cw cr out size chunk res
  if command -v flock >/dev/null; then
    exec 9>"$dir/lock"
    flock -n 9 || return
  else                                  # macOS has no flock; use mkdir
    if ! mkdir "$dir/lock.d" 2>/dev/null; then
      (( $(date +%s) - $(mtime "$dir/lock.d") < 60 )) && return
      rm -rf "$dir/lock.d"; mkdir "$dir/lock.d" 2>/dev/null || return
    fi
    trap "rmdir '$dir/lock.d' 2>/dev/null" EXIT
  fi
  export LC_ALL=C
  for f in "$tp" "${tp%.jsonl}"/subagents/*.jsonl; do
    [ -f "$f" ] || continue
    key=$dir/files/${f##*/}
    off=0 last=- i=0 cw=0 cr=0 out=0
    [ -f "$key" ] && read -r off last i cw cr out < "$key"
    [[ $off =~ ^[0-9]+$ && $i =~ ^[0-9]+$ && $cw =~ ^[0-9]+$ && $cr =~ ^[0-9]+$ && $out =~ ^[0-9]+$ ]] \
      || { off=0 last=- i=0 cw=0 cr=0 out=0; }
    size=$(( $(wc -c < "$f") ))
    (( size > off )) || continue
    chunk=$(tail -c +$((off + 1)) "$f" | head -c $((size - off)); echo x)
    chunk=${chunk%x}
    [[ $chunk == *$'\n'* ]] || continue
    chunk=${chunk%$'\n'*}$'\n'          # keep complete lines only
    res=$(printf '%s' "$chunk" | jq -R -s -r --arg last "$last" \
      --argjson s "[$i,$cw,$cr,$out]" '
      reduce (split("\n")[] | fromjson? | select(.type == "assistant")
              | .message | select(.usage != null)) as $m
        ({last: $last, s: $s};
         if $m.id == .last then . else
           .last = $m.id
           | .s[0] += ($m.usage.input_tokens // 0)
           | .s[1] += ($m.usage.cache_creation_input_tokens // 0)
           | .s[2] += ($m.usage.cache_read_input_tokens // 0)
           | .s[3] += ($m.usage.output_tokens // 0)
         end)
      | "\(.last) \(.s | map(tostring) | join(" "))"') || continue
    echo "$((off + ${#chunk})) $res" > "$key"
  done
  cat "$dir"/files/* 2>/dev/null | awk '{t += $3 + $4 + $5 + $6} END {print t + 0}' \
    > "$dir/total.tmp" && mv "$dir/total.tmp" "$dir/total"
}

# Start the token counter at most every 2 s. Without setsid (macOS) it stays
# in this process group and can be cancelled; the next run resumes the count.
TOTAL_TOK=""
if [ -n "$STATE" ]; then
  if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ] && (( NOW - $(mtime "$STATE/total") >= 2 )); then
    export -f update_tokens mtime
    DETACH=""; command -v setsid >/dev/null && DETACH=setsid
    $DETACH bash -c 'update_tokens "$@"' _ "$TRANSCRIPT" "$STATE" </dev/null >/dev/null 2>&1 &
  fi
  TOTAL_TOK=$(cat "$STATE/total" 2>/dev/null)
  [[ $TOTAL_TOK =~ ^[0-9]+$ ]] || TOTAL_TOK=""
fi

# Git status of tracked files, cached per session for 5 s (git is slow on NFS).
GIT_INFO=""
if [ -n "$CWD" ]; then
  CACHE="${STATE:+$STATE/git}"
  if [ -n "$CACHE" ] && [ -f "$CACHE" ] && (( NOW - $(mtime "$CACHE") < 5 )) \
     && [ "$(head -1 "$CACHE")" = "$CWD" ]; then
    GIT_INFO=$(sed -n 2p "$CACHE")
  else
    if ST=$(git -C "$CWD" --no-optional-locks status --porcelain=v2 --branch \
              --untracked-files=no 2>/dev/null); then
      BR="" OID="" AB="" DIRTY=""
      while IFS= read -r l; do
        case $l in
          "# branch.head "*) BR=${l#\# branch.head } ;;
          "# branch.oid "*)  OID=${l#\# branch.oid } ;;
          "# branch.ab "*)   set -- ${l#\# branch.ab }
                             (( ${1#+} > 0 )) && AB+=" ↑${1#+}"
                             (( ${2#-} > 0 )) && AB+=" ↓${2#-}" ;;
          "#"*) ;;
          *) DIRTY="*"; break ;;          # headers come first; one change is enough
        esac
      done <<< "$ST"
      [ "$BR" = "(detached)" ] && BR="@${OID:0:7}"
      GIT_INFO="${BR}${DIRTY}${AB}"
    fi
    [ -n "$CACHE" ] && printf '%s\n%s\n' "$CWD" "$GIT_INFO" > "$CACHE" 2>/dev/null
  fi
fi

# Task list of this session: completed / total.
TASKS=""
TASK_FILES=("$CONFIG_DIR/tasks/$SESSION"/*.json)
if [ -f "${TASK_FILES[0]}" ]; then
  DONE=$(( $(grep -lE '"status": *"completed"' "${TASK_FILES[@]}" 2>/dev/null | wc -l) ))
  TASKS="$DONE/${#TASK_FILES[@]}"
fi

# ── Line 1: model, effort, mode │ session name │ project git │ worktree │ PR │ vim
L1="${DIM}[${RST}${MODEL}"
[ -n "$EFFORT" ] && L1+=" ${DIM}·${RST} ${EFFORT}"
[ "$FAST" = "true" ] && L1+=" ${DIM}·${RST} ${CYAN}fast${RST}"
[ "$THINKING" = "false" ] && L1+=" ${DIM}· no-think${RST}"
L1+="${DIM}]${RST}"
[ -n "$SESS_NAME" ] && L1+="${SEP}${CYAN}${SESS_NAME}${RST}"
L1+="${SEP}${CWD##*/}"
[ -n "$GIT_INFO" ] && L1+=" ${DIM}git:(${RST}${GIT_INFO}${DIM})${RST}"
[ -n "$WT_NAME" ] && L1+="${SEP}${DIM}wt:${RST}${WT_NAME}"
[ -n "$PR_NUM" ] && L1+="${SEP}${DIM}PR${RST} #${PR_NUM}${PR_STATE:+ ${DIM}${PR_STATE}${RST}}"
[ -n "$VIM" ] && L1+="${SEP}${VIM}"
printf '%s\n' "$L1"

# ── Line 2: context vs auto-compact trigger │ 5h │ 7d │ spend limit
# Window: CLAUDE_CODE_AUTO_COMPACT_WINDOW (min 100K), else autoCompactWindow,
# else the model context window; capped at the model context window.
# Trigger: window - 20K summary reserve - 13K. CLAUDE_AUTOCOMPACT_PCT_OVERRIDE
# (1-100) can only lower it. With auto-compact off, show the window.
CTX_SIZE=${CTX_SIZE:-0} CTX_IN=${CTX_IN:-0} ACW=${ACW:-0}
WIN=$CTX_SIZE
if [[ $CLAUDE_CODE_AUTO_COMPACT_WINDOW =~ ^[0-9]+ ]]; then
  WIN=$(( 10#${BASH_REMATCH[0]} )); (( WIN < 100000 )) && WIN=100000
elif (( ACW > 0 )); then
  WIN=$ACW
fi
(( CTX_SIZE > 0 && WIN > CTX_SIZE )) && WIN=$CTX_SIZE
LIMIT=$WIN
if (( WIN > 33000 )) && [ "$AC_ON" != "false" ] && [ -z "$DISABLE_AUTO_COMPACT" ]; then
  EFF=$(( WIN - 20000 )); LIMIT=$(( EFF - 13000 ))
  if [[ $CLAUDE_AUTOCOMPACT_PCT_OVERRIDE =~ ^[0-9]+ ]]; then
    P=$(( 10#${BASH_REMATCH[0]} ))
    (( P >= 1 && P <= 100 && EFF * P / 100 < LIMIT )) && LIMIT=$(( EFF * P / 100 ))
  fi
fi
CTX_PCT=0
(( LIMIT > 0 )) && CTX_PCT=$(( CTX_IN * 100 / LIMIT ))
L2="  ${DIM}Context${RST} $(make_bar "$CTX_PCT") ${CTX_PCT}%"
(( LIMIT > 0 )) && L2+=" ${DIM}($(fmt_k "$CTX_IN")/$(fmt_k "$LIMIT"))${RST}"
if [ -n "$RL5" ]; then
  L2+="${SEP}${DIM}5h:${RST} $(make_bar "$RL5") ${RL5}%"
  [ -n "$RL5_AT" ] && L2+="${DIM} ($(fmt_dur $((RL5_AT - NOW))))${RST}"
fi
if [ -n "$RL7" ]; then
  L2+="${SEP}${DIM}7d:${RST} $(make_bar "$RL7") ${RL7}%"
  [ -n "$RL7_AT" ] && L2+="${DIM} ($(fmt_dur $((RL7_AT - NOW))))${RST}"
fi
[ -n "$SPEND" ] && L2+="${SEP}${DIM}spend:${RST} $(make_bar "$SPEND") ${SPEND}%"
printf '%s\n' "$L2"

# ── Line 3: tasks │ prompt cache │ total tokens │ total cost
L3=""
[ -n "$TASKS" ] && L3+="${DIM}tasks${RST} ${TASKS}${SEP}"
if [ -n "$PC_WARM" ]; then
  if [ "$PC_WARM" = "true" ]; then
    PC="${GREEN}warm${RST}"
    [ -n "$PC_EXP" ] && PC+="${DIM} $(fmt_dur $((PC_EXP - NOW)))${RST}"
  else
    PC="${YELLOW}cold${RST}"
  fi
  [ -n "$PC_HIT" ] && PC+=" ${DIM}hit${RST} ${PC_HIT}%"
  [ -n "$PC_MISS" ] && (( PC_MISS > 0 )) && PC+=" ${DIM}miss${RST} ${PC_MISS}"
  L3+="${DIM}cache${PC_TTL:+ ${PC_TTL}}:${RST} ${PC}${SEP}"
fi
if [ -n "$TOTAL_TOK" ]; then TOK_FMT=$(fmt_k "$TOTAL_TOK"); else TOK_FMT="…"; fi
COST=${COST:-0}
L3+="${DIM}tokens${RST} ${TOK_FMT}"
L3+="${SEP}${DIM}cost${RST} \$$((COST / 100)).$(printf '%02d' $((COST % 100)))"
printf '%s\n' "  $L3"
