# 上限で止まった会話を自動で再開する

使用量の上限に当たって会話が途中で止まったとき、上限が解除される時刻に、その会話を自動で再開する仕組みである。すべての会話が対象である。

## 動き

1. 会話が終わると、Claude Code が終了時の合図（`Stop` と `SessionEnd`）でこの仕組みを呼ぶ。
2. 呼ばれた側は受け取った情報をすぐ子の処理へ渡して戻る。会話の終了を待たせない。
3. 子の処理が会話の記録を末尾だけ読み、最後の発言が「上限に当たった」という文面かどうかを見る。ふつうの終了なら何もしない。
4. 上限だった場合は、文面の中の解除時刻（例「resets 9:10pm (Asia/Tokyo)」）を読み取り、少し余裕を足した時刻に一度だけ起きる予約を macOS へ登録する。
5. その時刻になると、元の作業場所へ移り、止まった会話をそのまま続きから動かす。画面は開かず、裏で走る。
6. 走り終えると予約は自分を消す。使い捨てである。

上限で止まったときにどちらの合図が出るかは決まっていないため、両方に仕掛けてある。二度呼ばれても、同じ予約は一度しか入らない。

## ファイル

| ファイル | 役割 |
| --- | --- |
| `config.json` | 有効・無効と各しきい値。変更するのはここだけでよい |
| `detect.mjs` | 上限で止まったかを判定し、解除時刻の予約を登録する |
| `resume.sh` | 予約の時刻に呼ばれ、会話を再開し、終わったら予約を消す |

呼び出しの設定は `~/.claude/settings.json` の `hooks` にある。

## 止め方

どちらか一方で仕組み全体が止まる。

- `config.json` の `enabled` を `false` にする。
- 環境変数 `CLAUDE_AUTO_RESUME` に `off`（`0`・`false` も可）を入れる。

すでに入っている予約も消したい場合は、次で一覧と削除ができる。

```shell
ls ~/Library/LaunchAgents | grep com.claude.auto-resume
launchctl bootout gui/$(id -u)/com.claude.auto-resume.<セッションID>
rm ~/Library/LaunchAgents/com.claude.auto-resume.<セッションID>.plist
```

## しきい値

`config.json` にまとめてある。

| 項目 | 既定 | 意味 |
| --- | --- | --- |
| `enabled` | `true` | 仕組み全体の有効・無効 |
| `maxResumesPerSession` | `3` | 同じ会話を再開する上限の回数。再開してすぐまた上限に当たる場合の空回りを防ぐ |
| `maxLimitAgeHours` | `12` | 上限に当たってからこの時間を過ぎた会話は対象外とする |
| `resetBufferMinutes` | `3` | 解除時刻に足す余裕 |
| `fallbackWaitMinutes` | `60` | 文面から解除時刻を読み取れないときに待つ時間 |
| `transcriptTailBytes` | `262144` | 会話の記録を末尾から読む量。記録が大きくても全部は読まない |
| `resumePrompt` | — | 再開したときに最初に渡す指示 |

## 記録

すべて git の管理外に残る。

- `~/.claude/resume-logs/detect.log` — 判定のたびに一行。何もしなかった理由もここに残る。
- `~/.claude/resume-logs/<予約時刻>_<セッションID>.log` — 再開した会話の出力。
- `~/.claude/auto-resume/state.json` — 会話ごとの再開回数。
