# 上限で止まった会話を自動で再開する

使用量の上限に当たって会話が止まったとき、上限が解除される時刻に、その会話を自動で再開する仕組みである。すべての会話が対象である。

## 動き

1. 会話が使用量の上限で止まると、Claude Code が `StopFailure` の合図（`rate_limit` のときだけ）でこの仕組みを呼ぶ。
2. 呼ばれた側は受け取った情報をすぐ切り離した子の処理へ渡して戻る。会話の終了を待たせない。
3. 子の処理が、合図が渡す `last_assistant_message`（画面に出た文字列そのもの）を見て判定する。
   - 上限の文面（`hit your ... limit`）でなければ何もしない。
   - 文面から解除時刻（例「resets 9:10pm (Asia/Tokyo)」）が読み取れなければ、仮の時刻は置かず何もしない。
   - その会話の再開回数が上限に達していれば何もしない。
   - 同じ予約が既にあれば何もしない。
4. どの場合も何もしなかった理由、または予約したことが記録に一行残る。
5. 予約する場合は、解除時刻に少し余裕を足した時刻に一度だけ起きる予約を macOS へ登録する。
6. その時刻になると、予約が元の作業場所へ移り、止まった会話をそのまま続きから動かす。画面は開かず、裏で走る。
   予約の時刻から大きく遅れて呼ばれた場合は、再開せず片付けるだけで終える。
7. 走り終えると、どう終えても予約は自分を消す。使い捨てである。

## ファイル

| ファイル | 役割 |
| --- | --- |
| `config.json` | 有効・無効と各しきい値。変更するのはここだけでよい |
| `detect.mjs` | 上限で止まったかを判定し、解除時刻の予約を登録する |
| `resume.sh` | 予約の時刻に呼ばれ、会話を再開し、終わったら予約を消す |

呼び出しの設定は `~/.claude/settings.json` の `hooks` の `StopFailure`（matcher `rate_limit`）にある。

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
| `resetBufferMinutes` | `3` | 解除時刻に足す余裕 |
| `resumePrompt` | — | 再開したときに最初に渡す指示 |

## 記録

すべて git の管理外に残る。

- `~/.claude/resume-logs/detect.log` — 判定のたびに一行。何もしなかった理由もここに残る。
- `~/.claude/resume-logs/<予約時刻>_<セッションID>.log` — 再開した会話の出力。
- `~/.claude/auto-resume/state.json` — 会話ごとの再開回数。
