#!/usr/bin/env bash
# Standalone Claude Code statusline — no claude-hud dependency

INPUT=$(cat)

# Parse JSON once
MODEL=$(echo "$INPUT" | jq -r '.model.display_name // .model.id // "Claude"')
CW=$(echo "$INPUT" | jq -c '.context_window // null')
CWD=$(echo "$INPUT" | jq -r '.cwd // ""')
MODEL_ID=$(echo "$INPUT" | jq -r '.model.id // ""')

# Project name from cwd
PROJECT=$(basename "$CWD" 2>/dev/null)

# Git status
GIT_BRANCH=""
if [ -n "$CWD" ] && [ -d "$CWD/.git" ] || git -C "$CWD" rev-parse --git-dir >/dev/null 2>&1; then
  GIT_BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null)
  GIT_DIRTY=""
  GIT_AHEAD=""
  if [ -n "$GIT_BRANCH" ]; then
    git -C "$CWD" diff --quiet 2>/dev/null || GIT_DIRTY="*"
    git -C "$CWD" diff --cached --quiet 2>/dev/null || GIT_DIRTY="*"
    AHEAD=$(git -C "$CWD" rev-list --count "@{upstream}..HEAD" 2>/dev/null || echo 0)
    BEHIND=$(git -C "$CWD" rev-list --count "HEAD..@{upstream}" 2>/dev/null || echo 0)
    [ "$AHEAD" -gt 0 ] 2>/dev/null && GIT_AHEAD+=" ↑${AHEAD}"
    [ "$BEHIND" -gt 0 ] 2>/dev/null && GIT_AHEAD+=" ↓${BEHIND}"
  fi
fi

# Colors
DIM="\033[2m"
RST="\033[0m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
MAGENTA="\033[35m"

# Helper: make a 10-char progress bar with color
make_bar() {
  local pct="$1"
  local filled=$(( pct / 10 ))
  local empty=$(( 10 - filled ))
  local bar=""
  for ((i=0; i<filled; i++)); do bar+="█"; done
  for ((i=0; i<empty; i++)); do bar+="░"; done
  local color="$GREEN"
  if [ "$pct" -ge 90 ]; then color="$RED"
  elif [ "$pct" -ge 70 ]; then color="$YELLOW"
  elif [ "$pct" -ge 50 ]; then color="$YELLOW"
  fi
  printf "${color}%s${RST}" "$bar"
}

# Helper: format duration from seconds
fmt_duration() {
  local secs="$1"
  local mins=$(( secs / 60 ))
  if [ "$mins" -ge 60 ]; then
    printf "%dh %dm" $(( mins / 60 )) $(( mins % 60 ))
  else
    printf "%dm" "$mins"
  fi
}

format_k() {
  local n="$1"
  if [ "$n" -ge 1000000 ]; then
    echo "${n}" | awk '{printf "%.1fM", $1/1000000}'
  elif [ "$n" -ge 1000 ]; then
    echo "${n}" | awk '{printf "%.1fK", $1/1000}'
  else
    echo "$n"
  fi
}

# Context percentage
PERCENT=0
if [ "$CW" != "null" ] && [ -n "$CW" ]; then
  PERCENT=$(echo "$CW" | jq -r '.used_percentage // 0' | awk '{printf "%d", $1}')
fi

# Line 1: Model | Project git:(branch*)
LINE1="${DIM}[${RST}${MODEL}${DIM}]${RST}"
if [ -n "$PROJECT" ]; then
  LINE1+=" ${DIM}│${RST} ${PROJECT}"
fi
if [ -n "$GIT_BRANCH" ]; then
  LINE1+=" ${DIM}git:(${RST}${GIT_BRANCH}${GIT_DIRTY}${GIT_AHEAD}${DIM})${RST}"
fi
printf "%b\n" "$LINE1"

# Line 2: Context bar │ 5h usage bar │ 7d usage bar
printf "  ${DIM}Context${RST} "
make_bar "$PERCENT"
printf " %d%%" "$PERCENT"

# Rate limits with bars
RL=$(echo "$INPUT" | jq -c '.rate_limits // null')
if [ "$RL" != "null" ] && [ -n "$RL" ]; then
  RL_5H=$(echo "$RL" | jq -r '.five_hour.used_percentage // empty' 2>/dev/null)
  RL_7D=$(echo "$RL" | jq -r '.seven_day.used_percentage // empty' 2>/dev/null)
  RL_5H_RESET=$(echo "$RL" | jq -r '.five_hour.resets_at // empty' 2>/dev/null)
  RL_7D_RESET=$(echo "$RL" | jq -r '.seven_day.resets_at // empty' 2>/dev/null)

  if [ -n "$RL_5H" ]; then
    RL_5H_INT=${RL_5H%.*}
    RL_5H_INT=${RL_5H_INT:-0}

    # Time remaining until reset
    RESET_5H_FMT=""
    if [ -n "$RL_5H_RESET" ]; then
      NOW_S=$(date +%s)
      REM=$(( RL_5H_RESET - NOW_S ))
      if [ "$REM" -gt 0 ] 2>/dev/null; then
        REM_H=$(( REM / 3600 ))
        REM_M=$(( (REM % 3600) / 60 ))
        RESET_5H_FMT=" (${REM_H}h ${REM_M}m)"
      fi
    fi

    printf " ${DIM}│ 5h:${RST} "
    make_bar "$RL_5H_INT"
    printf " %d%%${DIM}%s${RST}" "$RL_5H_INT" "$RESET_5H_FMT"
  fi

  if [ -n "$RL_7D" ]; then
    RL_7D_INT=${RL_7D%.*}
    RL_7D_INT=${RL_7D_INT:-0}

    # Time remaining until reset
    RESET_7D_FMT=""
    if [ -n "$RL_7D_RESET" ]; then
      NOW_S=${NOW_S:-$(date +%s)}
      REM=$(( RL_7D_RESET - NOW_S ))
      if [ "$REM" -gt 0 ] 2>/dev/null; then
        REM_D=$(( REM / 86400 ))
        REM_H=$(( (REM % 86400) / 3600 ))
        if [ "$REM_D" -gt 0 ]; then
          RESET_7D_FMT=" (${REM_D}d ${REM_H}h)"
        else
          REM_M=$(( (REM % 3600) / 60 ))
          RESET_7D_FMT=" (${REM_H}h ${REM_M}m)"
        fi
      fi
    fi

    printf " ${DIM}| 7d:${RST} "
    make_bar "$RL_7D_INT"
    printf " %d%%${DIM}%s${RST}" "$RL_7D_INT" "$RESET_7D_FMT"
  fi
fi
printf "\n"

# Line 3: Token breakdown + cost
if [ "$CW" != "null" ] && [ -n "$CW" ]; then
  TOTAL_INPUT=$(echo "$CW" | jq -r '.total_input_tokens // 0')
  TOTAL_OUTPUT=$(echo "$CW" | jq -r '.total_output_tokens // 0')
  CACHE_WRITE=$(echo "$CW" | jq -r '.current_usage.cache_creation_input_tokens // 0')
  CACHE_READ=$(echo "$CW" | jq -r '.current_usage.cache_read_input_tokens // 0')

  if [ "$TOTAL_INPUT" -gt 0 ] || [ "$TOTAL_OUTPUT" -gt 0 ]; then
    IN_FMT=$(format_k "$TOTAL_INPUT")
    OUT_FMT=$(format_k "$TOTAL_OUTPUT")
    CW_FMT=$(format_k "$CACHE_WRITE")
    CR_FMT=$(format_k "$CACHE_READ")

    # Cost calculation
    case "$MODEL_ID" in
      *opus-4*) P_IN="15.00"; P_CW="18.75"; P_CR="1.50"; P_OUT="75.00" ;;
      *sonnet-4*) P_IN="3.00"; P_CW="3.75"; P_CR="0.30"; P_OUT="15.00" ;;
      *haiku*) P_IN="0.80"; P_CW="1.00"; P_CR="0.08"; P_OUT="4.00" ;;
      *) P_IN="3.00"; P_CW="3.75"; P_CR="0.30"; P_OUT="15.00" ;;
    esac

    COST=$(echo "$TOTAL_INPUT $TOTAL_OUTPUT $CACHE_WRITE $CACHE_READ $P_IN $P_OUT $P_CW $P_CR" | awk '{
      input=$1; output=$2; cw=$3; cr=$4
      plain = input - cw - cr
      if (plain < 0) plain = 0
      cost = (plain * $5 + cw * $7 + cr * $8 + output * $6) / 1000000
      printf "%.2f", cost
    }')

    printf "  ${DIM}in:${RST}%s ${DIM}cw:${RST}%s ${DIM}cr:${RST}%s ${DIM}out:${RST}%s ${DIM}|${RST} \$%s\n" \
      "$IN_FMT" "$CW_FMT" "$CR_FMT" "$OUT_FMT" "$COST"
  fi
fi
