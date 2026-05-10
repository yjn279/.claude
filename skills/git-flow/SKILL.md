---
name: git-flow
description: git リポジトリの初期化、作業ブランチと worktree の切り出し、Pull Request による統合、ブランチ・worktree の後片付けまでを通したライフサイクル全体に関わるタスクで呼び出すスキル。「リポジトリを作りたい」「ブランチを切って worktree で作業したい」「PR を作ってマージしたい」「作業後のクリーンアップを忘れないようにしたい」という状況で必ず参照すること。
---

# Git Flow

このリポジトリにおける git 運用の基本方針を定める。対象は、新規リポジトリの立ち上げ、作業ブランチと worktree の切り出し、Pull Request 経由での統合と後片付けの 3 フェーズである。

## いつ使うか

次のいずれかに当てはまる状況でこのスキルを参照する。

- 新しいリポジトリを作成・初期化しようとしている
- 新しい作業に取りかかろうとしている、またはブランチ名の形式に迷っている
- ベースブランチの最新から worktree を切り出して並行作業したい
- `main` ブランチで直接作業しようとしている
- 変更を Pull Request としてリモートに統合したい
- 作業完了後にブランチや worktree を整理したい

## Initialization

新規リポジトリを初期化するフェーズである。`main` ブランチを起点に、空コミットで履歴を確立してから作業ブランチへ移行する流れを守る。

1. パブリックリポジトリとして公開し、デフォルトブランチ名を `main` に設定する。`master` は使わない。

   ```shell
   git init -b main
   ```

2. リポジトリ作成直後は、空コミットを作成してブランチを確立する。

   ```shell
   git commit --allow-empty -m "Initial commit"
   ```

3. `main` ブランチで直接作業してはいけない。PR ベースのレビューを通すこと、履歴を機能・修正単位で整理すること、問題発生時に特定コミットへ容易に戻れることを理由に、実際の作業はすべて `main` から切った作業ブランチ上で進める。ブランチ命名と worktree 作成は次節「Start」で扱う。

## Start

新しい作業を開始するフェーズである。命名規則に従ってブランチを定義し、ベースブランチの最新コミットから worktree を切り出す。worktree を分離することで、ブランチを切り替えずに並行作業や緊急対応に取りかかれる。

ブランチ名は `<type>/<description>` の形式とする。`<type>` はそのブランチで行う変更の種類、`<description>` は変更内容を表す。

`<type>` の代表例を以下に示す。

- `feat`: 新機能の追加
- `fix`: バグ修正
- `chore`: ビルドやツールなど、コードに直接関係しない変更
- `docs`: ドキュメントの変更
- `refactor`: 動作を変えないコードの整理・改善
- `test`: テストの追加や修正

`<description>` は kebab-case の英語短句とし、1〜5 語程度に収める。変更内容が一言で伝わる具体的な動詞句を選ぶ。人名・連番・日付スタンプ・`tmp`・`wip` のような意味を持たない語は避ける。

良いブランチ名の例: `feat/add-search-filter`、`fix/login-redirect-loop`
悪いブランチ名の例: `feature1`、`tmp`、`yuji-branch`、`20260509`

worktree は、ベースブランチ（既定では `origin/main`、指定があれば対象のブランチや対象 Pull Request に対応するブランチ）の最新コミットを起点として切り出す。同一ブランチに対する既存の worktree が残っている場合は新規作成せず、それを再利用する。

```shell
git fetch origin <base>
git worktree add -b <type>/<description> <path> origin/<base>
```

## Cleanup

作業を完了させ、リモートに統合してから環境を整えるフェーズである。レビューを経ずに勝手にマージしないこと、マージ後の残骸を放置しないことを徹底する。

1. 変更はリモートのベースブランチに対して push し、Pull Request を作成する。同一ブランチに対する既存の PR が open であれば、新規 PR を作らず追記 push に留める。

2. PR は独断でマージしない。必ずレビュー依頼を行い、承認を得てからスカッシュマージする。履歴を機能・修正単位で 1 コミットに集約するため、マージ方式は squash で固定する。

3. マージ後は関連するブランチと worktree を削除し、ローカル・リモートともクリーンな状態に戻す。

   ```shell
   git worktree remove <path>
   git branch -d <type>/<description>
   git push origin --delete <type>/<description>
   ```

## 例

次の例は、このスキルが対象とする典型的なフェーズ移行を示す。

### 例 1: 新規リポジトリの初期化

新しいプロジェクトを始めるために空のディレクトリでリポジトリを初期化し、最初の作業ブランチへ移行する。

```shell
git init -b main
git commit --allow-empty -m "Initial commit"
git switch -c feat/initial-setup
```

これにより `main` には空コミットだけが残り、実作業はすべて `feat/initial-setup` ブランチ上で行われる。

### 例 2: 既存リポジトリで worktree を切り出して作業を開始する

`main` の最新を取得し、`fix/login-redirect-loop` ブランチを `origin/main` から派生させて worktree にチェックアウトする。

```shell
git fetch origin main
git worktree add -b fix/login-redirect-loop ../login-redirect origin/main
cd ../login-redirect
```

### 例 3: PR を作成し、マージ後にクリーンアップする

変更を push して PR を作成し、レビュー承認後にマージしてからブランチと worktree を削除する。

```shell
git push -u origin fix/login-redirect-loop
gh pr create --fill
# レビュー承認後
gh pr merge --squash --delete-branch
git worktree remove ../login-redirect
```
