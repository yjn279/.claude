#!/bin/bash
# 予約の時刻に launchd から呼ばれ、止まった会話を元の作業場所で再開する。
# 走り終えたら自分の予約を消す使い捨てである。
set -uo pipefail

SESSION_ID="$1"
WORKDIR="$2"
CLAUDE_BIN="$3"
PROMPT="$4"
LABEL="$5"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 再開 ${SESSION_ID} @ ${WORKDIR}"
cd "$WORKDIR" || exit 1
"$CLAUDE_BIN" --resume "$SESSION_ID" --print "$PROMPT"
STATUS=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 終了 status=${STATUS}"

rm -f "$HOME/Library/LaunchAgents/${LABEL}.plist"
/bin/launchctl bootout "gui/$(id -u)/${LABEL}"
