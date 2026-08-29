#!/bin/bash
# 上限に当たるのを待たずに、仕組み全体をその場で確かめる。
# 使い捨ての会話を作り、それが終わる瞬間に上限の文面を流し込み、数分後に本当に再開されるかを見る。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
STATE="$CLAUDE_HOME/auto-resume/state.json"
# 許可の要る場所を通ることまで含めて確かめるため、書類フォルダの下で試す。
WORKDIR="$HOME/Documents/auto-resume-check"
TMP="$(mktemp -d)"
BUFFER=$(python3 -c "import json;print(json.load(open('$HERE/config.json'))['resetBufferMinutes'])")

field() { python3 -c "import json;print(json.load(open('$1')).get('$2',{}).get('$3') or '')" 2>/dev/null; }

cleanup() {
  [ -n "${WAITER:-}" ] && kill "${WAITER}" 2>/dev/null
  [ -n "${SESSION:-}" ] && python3 - "$STATE" "${SESSION}" <<'PY' 2>/dev/null
import json, sys
path, session = sys.argv[1], sys.argv[2]
state = json.load(open(path))
state.pop(session, None)
json.dump(state, open(path, "w"), ensure_ascii=False, indent=2)
PY
  [ -n "${PROJECT:-}" ] && rm -rf "${PROJECT}"
  rm -rf "$TMP" "$WORKDIR"
}
trap cleanup EXIT

# 会話が終わる瞬間に呼ばれ、その場の情報をそのまま上限の文面に差し替えて仕組みへ渡す。
cat > "$TMP/shim.py" <<PY
import datetime, json, subprocess, sys, pathlib
payload = json.load(sys.stdin)
pathlib.Path("$TMP/payload.json").write_text(json.dumps(payload))
at = datetime.datetime.now() + datetime.timedelta(minutes=1)
payload["hook_event_name"] = "StopFailure"
payload["last_assistant_message"] = "You've hit your session limit · resets " + at.strftime("%-I:%M%p").lower()
subprocess.run(["$HERE/detect.mjs"], input=json.dumps(payload), text=True)
PY
cat > "$TMP/settings.json" <<EOF
{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"python3 $TMP/shim.py","timeout":15}]}]}}
EOF

echo "1. 使い捨ての会話を $WORKDIR に作り、終わる瞬間に上限の文面を流し込む"
mkdir -p "$WORKDIR"
(cd "$WORKDIR" && claude --settings "$TMP/settings.json" -p "確認用の会話です。「はい」とだけ返せ。" >/dev/null 2>&1)
if [ ! -s "$TMP/payload.json" ]; then echo "   失敗: 会話を作れなかった"; exit 1; fi
SESSION=$(python3 -c "import json;print(json.load(open('$TMP/payload.json'))['session_id'])")
PROJECT=$(python3 -c "import json,os;print(os.path.dirname(json.load(open('$TMP/payload.json'))['transcript_path']))")
echo "   会話 ${SESSION} は終了済み"
sleep 3

echo "2. 会話が消えた後も待ち続けているか"
WAITER=$(field "$STATE" "$SESSION" pid)
SCHEDULED=$(field "$STATE" "$SESSION" scheduledFor)
if [ -z "${WAITER}" ]; then
  echo "   失敗: 待機が始まらなかった。理由は次の行にある"
  tail -1 "$CLAUDE_HOME/resume-logs/detect.log"
  exit 1
fi
echo "   ${SCHEDULED} まで待つ処理が生きている（番号 ${WAITER}）"

echo "3. その時刻まで待つ（$((BUFFER + 1)) 分ほど）"
for _ in $(seq 1 120); do
  RESULT=$(field "$STATE" "$SESSION" result)
  [ -n "${RESULT}" ] && break
  sleep 10
done

echo "4. 結果"
if [ -z "${RESULT:-}" ]; then echo "   失敗: 時間内に再開されなかった"; exit 1; fi
tail -1 "$CLAUDE_HOME/resume-logs/detect.log"
case "${RESULT}" in
  "再開の終了コード 0") echo "   成功: 上限で止まった会話は自動で再開される";;
  *) echo "   失敗: ${RESULT}"; exit 1;;
esac
