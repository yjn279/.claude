# personal `~/.claude/` config

このリポジトリは **そのまま `~/.claude/` の中身として動かす** ための個人設定リポジトリである。

## ディレクトリ構成

```shell
.
├── plugins/
│   ├── claude-plugins-official/    # git submodule → anthropics/claude-plugins-official
│   └── knowledge-work-plugins/     # git submodule → anthropics/knowledge-work-plugins
├── skills/
│   ├── trinity/                    # subtree → https://github.com/yjn279/trinity（git 履歴ごと取り込み）
│   │                               #   Trinity ハーネス（Planner → Generator → Evaluator）
│   ├── git-flow/                   # git 運用（ブランチ・worktree・PR・クリーンアップ）
│   ├── markdown/                   # Markdown 執筆ルール
│   └── humanizer/                  # git submodule → https://github.com/blader/humanizer
├── settings.json                   # 個人用フックと dev ツールの permissions
├── .gitmodules
└── README.md
```

## ランタイム artifacts

`trinity` スキルは **実行プロジェクトのルート** に `.trinity/<run>/` を作って worktree とログを置く。`~/.claude/` 配下にはランタイム成果物を一切作らない。

## 参考

- Claude Code: Explore the .claude directory — https://code.claude.com/docs/en/claude-directory
- Claude Code: Create plugins — https://code.claude.com/docs/en/plugins.md
- Claude Code: Sub agents — https://code.claude.com/docs/en/sub-agents
