---
name: trinity
description: Planner → Generator → Evaluator の3エージェント・ハーネスを直列に回し、Production-Ready の品質水準に達するまでイテレーションして実装・コミットし、Pull Request を作成するスキル。長時間かつ高品質が要求される実装タスクをユーザーが依頼したとき（「Trinity で実装して」「3エージェントで回して」「計画→実装→評価のループで進めて」など）に使う。要件文（1〜4 文）を引数として受け取る。
---

# Trinity — 3エージェント・ハーネス

Trinity は、AI エージェントが Production-Ready の品質水準を満たしつつ長時間の業務を遂行するためのハーネスである。Planner・Generator・Evaluator の3サブエージェントと、それらを統括するオーケストレーター（このスキルを読み込んだ本体）で構成する。Planner の作業計画をもとに、Production-Ready に達するまで Generator と Evaluator が GAN のように相互作用することで、品質の高い業務を遂行する。

- **Planner** — ユーザーの要望を作業計画に展開する。
- **Generator** — 計画に沿ってチャンク単位で実装し、コミットする。
- **Evaluator** — 実装が品質を満たすか独立に判定する。

オーケストレーターはコードに触れない。コードの変更は必ず Generator に委譲する。

## 入力

要件文（1〜4 文）を引数として受け取る。引数が空の場合は、ユーザーに要件を求めて停止する。

## 前提・プリフライト

起動時に次を満たすことを確認する。これは旧プラグイン版の hook が担っていた検査であり、スキル化に伴いオーケストレーター本体が実行する。

1. カレントが git リポジトリであること（`git rev-parse --git-dir`）。違えば停止して報告する。
2. ワーキングツリーが clean であること（`git status --porcelain` が空）。汚れていればコミットまたは stash を促して停止する。
3. 実行プロジェクトのルートに `.trinity/` とログを用意する。

   ```bash
   mkdir -p .trinity && touch .trinity/trinity.log
   ```

この時点で「現在のブランチが clean なベースライン」であることを保証する。worktree・ログ・計画ファイルなどのランタイム成果物は**実行プロジェクト側**の `.trinity/<run>/` に置き、この設定リポジトリには一切作らない。

## サブエージェントの起動

Planner / Generator / Evaluator は、（プラグイン時代のような登録済みエージェント型ではなく）このスキルの `references/` に置いたシステムプロンプトとして提供する。各サブエージェントは Task ツールで起動し、対応する参照ファイルの内容を動作指示として渡す。

| サブエージェント | システムプロンプト | model |
| --- | --- | --- |
| Planner | `references/planner.md` | opus |
| Generator | `references/generator.md` | sonnet |
| Evaluator | `references/evaluator.md` | sonnet |

守るべき不変ルール。

- **直列・同期で呼ぶ** — 各段は前段の成果ファイルに依存するため、並列化しない。Generator のチャンクも直列。
- **出力を要約しない** — Generator の検証レポートなどは圧縮せず、本文をそのまま次段へ渡す。
- **変数を漏れなく渡す** — 各段に必要な `RUN_DIR` / `WORKTREE_DIR` / `BRANCH` / `Iteration` / `ChunkIndex` / `ChunkTotal` / `ChunkFiles` / 最終コミット SHA などを渡す。

## 手順

1. **作業環境の構築** — `git-flow` スキルに基づき、隔離 worktree と作業ブランチを構築する。すでに構築済みの場合はそれを利用する。

2. **イテレーションの実行** — サブエージェントを直列・同期で呼び、作業を実行する。途中再開の場合は、完了済みの最新イテレーションの次から再開する。

   1. **Planner** — 要件を `${RUN_DIR}/plan.md` に展開する。実装タスクをコミット単位で独立検証可能な最小チャンク `M` に分割する。
   2. **Generator（チャンクごと）** — `i = 1..M` の順で起動し、各チャンクを実装してコミットする。1チャンクの実装が完了するごとに、次チャンク用の Generator を新たに起動する。
   3. **Evaluator** — 全チャンク完了後、イテレーション内の最終コミット SHA を取得して渡し、妥協なく評価させる。

      ```bash
      LAST_SHA=$(git -C "$WORKTREE_DIR" rev-parse HEAD)
      ```

   オーケストレーターは `${WORKTREE_DIR}` 内のコードに触れない。

3. **次回イテレーションの判断** — Evaluator の判定に従って後続対応を決める。

   | 判定 | 動作 |
   | --- | --- |
   | `PASS` | ループ脱出。次の手順へ進む。 |
   | `NEEDS_REVISION` | 続行。Planner が次周回で `plan.md` を上書きする。 |
   | `FAIL` | 続行。Generator が修正作業を実施する。 |

4. **Pull Request の作成** — `git-flow` スキルに従い PR を作成する。既存の PR がある場合は、そこへ追加で push し、変更点をコメントとして記載する。本文は次のテンプレートに沿う（title は本文に記載しない）。

   ```markdown
   ## 目的

   ## 実装内容

   ## 変更点サマリ
   ```

5. **修正判断のヒアリング** — PR の URL をユーザーへ共有し、`AskUserQuestion` で修正要否を仰ぐ。修正が必要な場合は手順 2 以降に戻る。不要な場合は手順 6 へ進む。

6. **対象リポジトリの課題起票** — ユーザーからの要望があった、または Trinity 自体が改善すべき課題を見つけた場合は、`AskUserQuestion`（`multiSelect=true`）で**対象リポジトリ**への課題起票を提案する。候補をすべて提示し、ユーザーが選択した課題のみを起票する。

   ```bash
   gh issue create --repo <owner/repo> --title "<title>" --body "<body>"
   ```

7. **Trinity の課題起票** — 同様に、Trinity 本体が改善すべき課題を `AskUserQuestion`（`multiSelect=true`）で提案し、選択された課題のみを起票する。

   ```bash
   gh issue create --repo yjn279/trinity --title "<title>" --body "<body>"
   ```

8. **クリーンアップ** — ユーザーから明示的な許可を得たら、`git-flow` に従い環境をクリーンアップする。あわせて `.trinity/` 内の該当 run フォルダを削除する。

## 依存

- **`git-flow` スキル**（このリポジトリ内 `skills/git-flow`）— 作業環境の構築・PR 作成・クリーンアップを委譲する。
- **`references/{planner,generator,evaluator}.md`** — 3サブエージェントのシステムプロンプト。
- **事前承認済みの権限** — `git worktree` / `git push` / `gh pr *` などを `settings.json` の `permissions.allow` に登録しておくと、ハーネスがプロンプトで中断しない。
