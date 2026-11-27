---
name: session-kickoff
description: Starts a task in its own Claude Code background session (claude --bg) with Remote Control, so the user can open and continue it from the Claude Desktop sidebar, claude.ai/code, or a phone. Pins the session so it keeps waiting for the user instead of being stopped, and unpins it once the caller says it is no longer needed. Use whenever a scheduled task, a skill, or the user hands work to a separate session that should keep running on this computer (「セッションを立てて」「別のセッションで進めて」「バックグラウンドで任せて」「スマホから続けられるように始めて」), including the scheduled tasks auto-review and do3.
---

# Session Kickoff

## Overview

作業 1 件ごとに Claude Code の背景セッション（ `claude --bg` ）を Remote Control 付きで始め、本人の返事を待つ間も止まらないよう固定し、要らなくなったら固定を外す。呼び出し側（定期タスク、ほかの Skill、本人の依頼）は、場所のフォルダ、指示の中身、追加の引数、固定するかどうか、固定を外す条件を決める。この Skill は、始め方、見つけ方、固定の仕組みを受け持つ。固定するのは、固定を外す条件を持つ呼び出し側だけである。本人が直接頼んだセッションは固定しない。

背景セッションを動かす常駐のプロセスは、Remote Control 付きのセッションが入力を待ったまま `8` 時間たつと、そのセッションを止める。Remote Control のないセッションは `1` 時間で止める。止まったセッションは Remote Control が切れ、サイドバーや claude.ai から続けられない。固定したセッションは止められない。ただしメモリが足りないときは、固定したセッションも最後に止められる。

セッションに名前は付けない。セッションは指示の文面で見つけるので、呼び出し側は、自分のセッションだけが含む目印（「定期タスク Auto Review が始めた」のような一文や、Issue の URL）を指示に書く。

固定と指示の読み書きに `jq` を使う（ `jq --version` で確かめる）。

## Start

CLI のログインを確かめ、指示のファイルを書いてから、セッションを始める。

1. `claude auth status` で CLI のログインを確かめる。ログインしていなくても `claude --bg` はセッションを作り、動かないまま待たせるため、先に確かめる。`loggedIn` が `true` でなければ、どのセッションも始めずに止め、「CLI へのログインが必要（ `claude auth login` ）」と呼び出し側に返す
2. 呼び出し側の決めた中身と置き場所で、指示のファイルを書く
3. 場所のフォルダで背景セッションを始める

```bash
cd "<フォルダ>" && claude --bg --remote-control -w <追加の引数> --permission-mode auto "$(cat <指示のファイル>)"
```

`--remote-control` で、Claude Desktop のサイドバー、claude.ai/code、スマホから開けるようにする。Git のリポジトリでは `-w` で、名前を自動で付けた新しい worktree を作り、手元のブランチや変更に触れないようにする。Git のリポジトリでないフォルダでは `-w` を付けない。`--remote-control` と `-w` は値を省ける引数なので、指示の直前に置かない。指示の直前は `--permission-mode auto` にする。

出力の `backgrounded · <id> · <表示名>` の `<id>` が、セッションを開いたり消したりするときの値である。この行が出ても、セッションは動き出す前に失敗することがあるので、数秒おいて状態を読む。

```bash
sleep 5 && jq -r '[.state, .detail] | @tsv' ~/.claude/jobs/<id>/state.json
```

出力に `backgrounded` の行がないときと、状態が `failed` のときは、始められなかったものとする。呼び出し側には、指示のファイルのパスに、行がないときは出力の全文を、`failed` のときは `detail` を添えて返す。

## Find

セッションの指示は `~/.claude/jobs/<id>/state.json` の `intent` にある。同じ作業のセッションがあるかは、指示が目印を含むセッションを探して確かめる。`claude rm` で消したセッションは出てこない。

```bash
jq -r --arg mark '<目印>' 'select((.intent // "") | contains($mark)) | [(input_filename | split("/")[-2]), .state, .cwd] | @tsv' ~/.claude/jobs/*/state.json
```

出力は `1` 行に `1` セッションで、id、状態、場所のフォルダをタブで区切って書いてある。指示の全文は `jq -r .intent ~/.claude/jobs/<id>/state.json` で読む。

## Pin

呼び出し側が固定すると決めたセッションは、始めたらすぐに `<id>` を固定する。固定は `~/.claude/jobs/pins.json` に書く id の配列で、`claude agents` の一覧で `ctrl+t` を押したときと同じ記録である。固定できなかったときは、エラーを呼び出し側に返す。

```bash
jq --arg id '<id>' '(. - [$id]) + [$id]' ~/.claude/jobs/pins.json > ~/.claude/jobs/pins.json.tmp && mv ~/.claude/jobs/pins.json.tmp ~/.claude/jobs/pins.json
```

## Unpin

呼び出し側は実行のたびに、自分が固定したセッションのうち、要らなくなったものの固定を外す。固定を外したセッションは、入力を待ったまま `8` 時間たつと止まる。

固定されている id ごとに、指示の有無と、目印を含むかを確かめる。

```bash
jq -r '.[]' ~/.claude/jobs/pins.json | while read -r id; do
  f=~/.claude/jobs/$id/state.json
  if [ -f "$f" ]; then jq -r --arg id "$id" --arg mark '<目印>' 'select((.intent // "") | contains($mark)) | $id' "$f"; else printf '%s\t消えた\n' "$id"; fi
done
```

| 出力 | 扱い |
| :-- | :-- |
| `消えた` と出た（ `claude rm` で消えた） | 固定を外す |
| 目印を含む | 指示の全文を読み、呼び出し側の条件に当てはまれば固定を外す。条件を確かめられなければ固定を残し、エラーを呼び出し側に返す |
| 出てこない | ほかの呼び出し側や本人が固定したものなので触れない |

```bash
jq --arg id '<id>' '. - [$id]' ~/.claude/jobs/pins.json > ~/.claude/jobs/pins.json.tmp && mv ~/.claude/jobs/pins.json.tmp ~/.claude/jobs/pins.json
```

## Operations

本人がターミナルで使う操作を次に示す。

| 操作 | コマンド |
| :-- | :-- |
| 開く | `claude attach <id>` |
| 止まったセッションを、同じ claude.ai の URL のまま再開する | `claude respawn <id>` |
| 作業を終えたセッションを、worktree ごと消す | `claude rm <id>` |
