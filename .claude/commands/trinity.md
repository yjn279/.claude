---
description: Planner → Generator → Evaluator のハーネスパイプラインを実行する。使用例 `/trinity <要件メモ>` または `/trinity --max-iter=5 <要件メモ>`。
argument-hint: [--max-iter=N] <要件メモ（任意・長さ不問）>
---

# /trinity — 3エージェント・ハーネスパイプライン

ハーネスを取り回すスラッシュコマンドである。起動時にユーザーへヒアリングを行い、Plannerが要件を計画に展開し、Generatorが隔離された worktree で実装してコミットし、Evaluatorが独立に判定する。判定が PASS になるか、`max_iter` に到達するまで繰り返す。最終 PASS 後、worktree のブランチを push して PR を作成する。

## 引数

生の引数は `$ARGUMENTS` で受け取る。次の手順で解釈する。

`$ARGUMENTS` の先頭が `--max-iter=N`（N は正の整数）であれば、`MAX_ITER = N` とし、そのトークンを取り除く。先頭が一致しない場合は `MAX_ITER = 15`（既定値）を使う。

残りを「要件メモ」として扱う。長さは問わない。空でも可。短い1行メモでも、長文の仕様書でも、そのまま次のヒアリング段に渡す。

## 起動時ヒアリング（AskUserQuestion）

run ディレクトリを切る前に、Claude の `AskUserQuestion` ツールで要件を詳しく聞き取る。要件メモが空でも、長文でも、必ず実施する（長文の場合は曖昧さの残る点だけを絞り込む）。質問はフリーテキストで投げず、必ず `AskUserQuestion` を使う。これを再実装したり、自前で対話プロンプトを書いたりしない。

呼び出し方は次のとおり。

- 1回の呼び出しに1〜4問をまとめて入れる。複数回に分けない。
- 各問は2〜4個の互いに排他的な選択肢を持つ。`AskUserQuestion` が自動で「Other」（自由入力）を付ける。
- 安全側・標準的な選択肢には末尾に `(Recommended)` を付け、リストの先頭に置く。
- 質問の典型例：スコープの粒度、UI の有無と形式、互換性の扱い、既存パターンの選択、テストの厚み。

要件メモを読んだ時点で一意に解釈できる項目は質問しない。確認のための確認は禁止する。

ヒアリングの回答とユーザーが投入した要件メモを統合した「確定要件」を作り、これを Planner に渡す。確定要件は記憶ではなくテキストとして保持し、次節で生成する `RUN_DIR` 直下に `${RUN_DIR}/intake.md` として書き出す。Planner はこのファイルを読む。

## プリフライト

ワーキングツリーが汚れていても問題ない。Trinity は隔離 worktree の中だけで作業し、ホスト側の作業ツリーには触れないためである。ベースは現在ブランチではなく、常に最新の `origin/main` を使う。

`/trinity` 起動直後に次を行う。

- カレントが git リポジトリであることを確認する。違えば停止してユーザーに報告する。
- リモートを fetch して base ref を確定する。`BASE_BRANCH` は PR の base 指定に、`BASE_REF` は worktree の出発点として使い分ける。

```shell
git rev-parse --git-dir >/dev/null 2>&1 || { echo 'trinity: not inside a git repository.' >&2; exit 1; }
git fetch origin main --quiet
BASE_BRANCH=main
BASE_REF=origin/main
```

`origin/main` が取得できない（リモートが無い・main が無い等）場合は、その旨を明示してユーザーに停止報告する。

## run ディレクトリと worktree の作成

確定要件からスラッグを生成し、run ディレクトリと隔離 worktree を作る。スラッグは2〜5語の英字 kebab-case にする（例: 「ユーザー設定ページにテーマトグルを追加する」→ `add-theme-toggle`）。`${RUN_DIR}/intake.md` には、上記ヒアリングで確定した要件本文をそのまま書き出す。

```shell
TS=$(date -u +%Y%m%dT%H%M%SZ)
SLUG=<要件から生成した英字 kebab-case>
RUN_DIR="$(pwd)/.trinity/${TS}-${SLUG}"
WORKTREE_DIR="${RUN_DIR}/worktree"
BRANCH="trinity/${TS}-${SLUG}"
mkdir -p "$RUN_DIR"
git worktree add -b "$BRANCH" "$WORKTREE_DIR" "$BASE_REF"
printf '=== %s run started on %s (base=%s) ===\n' "${TS}-${SLUG}" "${BRANCH}" "${BASE_REF}" >> .trinity/trinity.log
```

同一タイムスタンプで衝突した場合は `SLUG` の末尾に `-2` `-3` などを付ける。

`$RUN_DIR` と `$WORKTREE_DIR` と `$BRANCH` と `$BASE_BRANCH` を以降の全段に絶対パスで渡す。

## パイプライン（n = 1 .. MAX_ITER のループ）

### Planner

`planner` サブエージェントを次の入力で起動する。

- `INTAKE: ${RUN_DIR}/intake.md`（確定要件。原文ママを保持）
- `Iteration: <n>`
- `RUN_DIR: <絶対パス>`
- `WORKTREE_DIR: <絶対パス>`（実装対象のコードはこの中にある）
- `n > 1` の場合は、直前の評価レポートが `${RUN_DIR}/eval-<n-1>.md` にある旨を伝える

要件は要約せずに `intake.md` を Planner に直接読ませる。返却された計画ファイルパス（必ず `${RUN_DIR}/plan.md`）を保持する。Planner が `AskUserQuestion` でユーザーに追加確認を投げた場合は、その内容をユーザーに見せて停止する（Planner は他の対話手段を使ってはならない）。

### Generator

`generator` サブエージェントを次の入力で起動する。

- `RUN_DIR: <絶対パス>`
- `WORKTREE_DIR: <絶対パス>`
- `BRANCH: <ブランチ名>`
- `Iteration: <n>`

Generator は `${RUN_DIR}/plan.md` を読み、`n > 1` の場合は `${RUN_DIR}/eval-<n-1>.md` も読む。コードの読み書きとコミットは `${WORKTREE_DIR}` の中だけで行う。返却された検証レポートとコミットSHAを保持する。Generatorが検証失敗で自力修正もできずコミットを作れなかった場合は、停止して失敗内容をユーザーに報告する。存在しないコミットを Evaluator に渡してはいけない。

### Evaluator

`evaluator` サブエージェントを次の入力で起動する。

- `RUN_DIR: <絶対パス>`
- `WORKTREE_DIR: <絶対パス>`
- `Iteration: <n>`
- コミットSHA
- Generatorの検証レポート

返却された評価レポートのパス（必ず `${RUN_DIR}/eval-<n>.md`）と判定（PASS / NEEDS_REVISION / FAIL）を保持する。

### 分岐

PASS の場合はループを抜けて「最終化」セクションに進む。

NEEDS_REVISION で `n < MAX_ITER` の場合はループを継続する。Plannerは次の周回で評価レポートを受け取り、計画ファイルを新規作成せず上書きする。

FAIL の場合も同じく次の周回に進む。Plannerはより踏み込んだ再計画を行う。

`n == MAX_ITER` で PASS になっていない場合は最終化をスキップし、最新の評価レポートのパスと未解決の指摘を表示して停止する。終了行をログに書く。

```shell
printf '=== %s run ended: %s at iter %d/%d ===\n' "${TS}-${SLUG}" "${VERDICT}" "$n" "$MAX_ITER" >> .trinity/trinity.log
```

## 最終化（PASS のときだけ）

PASS で抜けたら次を順に行う。

1. ログに完了行を書く。

```shell
printf '=== %s run ended: PASS at iter %d ===\n' "${TS}-${SLUG}" "$n" >> .trinity/trinity.log
```

2. worktree のブランチを origin に push する。失敗はネットワーク要因のときのみ最大4回 exponential backoff で再試行する（2s, 4s, 8s, 16s）。それ以外の失敗（権限・ブランチ保護など）はそのまま停止してユーザーに報告する。

```shell
git -C "$WORKTREE_DIR" push -u origin "$BRANCH"
```

3. PR を作成する。`/trinity` の起動自体がパイプライン全体（PR作成を含む）への明示的な許可なので、ユーザー確認は取らずに進める。

PR の作成には GitHub MCP ツールを使う。スキーマが未ロードなら最初に `ToolSearch query="select:mcp__github__create_pull_request"` で読み込む。リポジトリ owner/repo は `git -C "$WORKTREE_DIR" remote get-url origin` から取り出す。

PR のタイトルは `${RUN_DIR}/plan.md` の先頭 H1 をそのまま使う。70 文字を超えるなら冒頭で切り詰める。

PR の本文は次の形にする。`.trinity/` は gitignore されておりレビュアーから見えないため、計画と判定の核心は本文に埋め込む。

```
## 概要
<plan.md の "目的" セクション本文をそのまま貼る>

## 受け入れ基準
<plan.md の "受け入れ基準" セクションを箇条書きでそのまま貼る>

## Trinity 実行サマリ
- Run: <RUN_DIR を repo ルートからの相対パスで>
- Iterations: <n>/<MAX_ITER>
- Final verdict: PASS
- Final commit: <短縮SHA>

## 判定根拠（最終 Evaluator レポートからの抜粋）
<eval-<n>.md の "判定" セクションをそのまま貼る>
```

base は `$BASE_BRANCH`、head は `$BRANCH` とする。

## ユーザーへの出力

ループ終了時に次の形式でちょうど印字する。最終化を実施した場合は最後に PR 行を加える。

```shell
Trinity result: <PASS | NEEDS_REVISION at iter <n> | FAIL at iter <n>>
RunDir:  <RUN_DIR>
Branch:  <BRANCH> (base: <BASE_BRANCH>)
Plan:    <RUN_DIR>/plan.md
Commit:  <最後のコミットSHA>
Eval:    <RUN_DIR>/eval-<n>.md
Iters:   <n>/<MAX_ITER>
PR:      <PR URL>            # PASS のときのみ
```

その後に2〜3文の平易な要約を添える。それ以上は書かない。

## オーケストレーター（あなた）への制約

サブエージェントは並列ではなく直列に呼び出す。各段は前段の出力に依存するためである。

段と段のあいだで、コードを自分で読んだり編集したりしない。受け渡しは `RUN_DIR` `WORKTREE_DIR` `BRANCH` のパスとコミットSHAだけにする。各エージェントが成果物（ファイル）から動くという原則がハーネスの本質である。

エージェントの出力を要約して次のエージェントに渡さない。`RUN_DIR` を渡し、次のエージェントに自分で読ませる。Evaluatorに必要な独立性はこれで担保される。

worktree の後始末は行わない。`.trinity/` は gitignore されており、worktree は監査ログとして残す。ユーザーが不要と判断したときに `git worktree remove` する。
