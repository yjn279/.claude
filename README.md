# personal `~/.claude/` config

このリポジトリは **そのまま `~/.claude/` の中身として動かす** ための個人設定リポジトリである。

## 追跡対象の方針

`~/.claude/` は Claude Code のライブディレクトリであり、セッションキャッシュ・テレメトリ・プラグインキャッシュなど機械生成のランタイムデータを大量に含む。そのため `.gitignore` は `/*` で全ファイルを無視し、バージョン管理したいものだけを許可リストで明示的に追跡する方式を採っている。

現在追跡しているのは `.github/` 、 `.gitignore` 、 `.gitmodules` 、 `README.md` 、 `settings.json` 、 `skills/` の 6 項目である。

## 構成

`skills/` 配下には Claude Code が参照するスキル定義を置く。現在の構成は次のとおりである。

- `skills/git-flow/SKILL.md` — ブランチ命名・worktree 管理・PR フローを定める git 運用スキル
- `skills/markdown/SKILL.md` — Markdown 記法の記述規約スキル
- `skills/humanizer/` — 文章を自然な表現に整える humanizer スキル（git submodule）

プラグインはこのリポジトリでは追跡していない。有効なプラグインは `settings.json` の `enabledPlugins` と `extraKnownMarketplaces` で管理し、marketplace 経由でインストールされる。

## settings.json

`permissions.defaultMode` で Claude Code のデフォルト操作モードを設定し、 `enabledPlugins` で有効化するプラグインを列挙する。 `extraKnownMarketplaces` には公式 marketplace に存在しないカスタム配信元（例: `yjn279/trinity`）を登録する。

## ランタイム artifacts

`/trinity:run` は **実行プロジェクトのルート** に `.trinity/<run>/` を作って worktree とログを置く。 `~/.claude/` をプロジェクトとして実行した場合は `~/.claude/.trinity/` 配下に成果物が作られるが、このディレクトリは `.gitignore` の対象であるため追跡されない。

## 参考

Claude Code の公式ドキュメントを以下に示す。

- Claude Code: Explore the .claude directory — https://code.claude.com/docs/en/claude-directory
- Claude Code: Create plugins — https://code.claude.com/docs/en/plugins.md
- Claude Code: Sub agents — https://code.claude.com/docs/en/sub-agents
