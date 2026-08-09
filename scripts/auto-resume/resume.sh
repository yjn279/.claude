#!/bin/bash
# 予約の時刻に launchd から呼ばれ、止まった会話を元の作業場所で再開する。
# 走り終えたら、どう終えても自分の予約を消す使い捨てである。
set -uo pipefail

readonly LATE_LIMIT_SECONDS=3600

SESSION_ID="$1"
WORKDIR="$2"
CLAUDE_BIN="$3"
PROMPT="$4"
LABEL="$5"
SCHEDULED_AT="$6"

cleanup() {
  rm -f "$HOME/Library/LaunchAgents/${LABEL}.plist"
  /bin/launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1
}
trap cleanup EXIT

DELAY=$(( $(date '+%s') - SCHEDULED_AT ))
if [ "$DELAY" -gt "$LATE_LIMIT_SECONDS" ]; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ${SESSION_ID}: 予約時刻から ${DELAY} 秒遅れたため再開せず片付ける"
  exit 0
fi

cd "$WORKDIR" || { echo "=== $(date '+%Y-%m-%d %H:%M:%S') ${SESSION_ID}: 作業場所 ${WORKDIR} へ移れない"; exit 1; }
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 再開 ${SESSION_ID} @ ${WORKDIR}"
"$CLAUDE_BIN" --resume "$SESSION_ID" --print "$PROMPT"
STATUS=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 終了 status=${STATUS}"
