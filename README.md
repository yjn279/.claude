# personal `~/.claude/` config

このリポジトリは **そのまま `~/.claude/` の中身として動かす** ための個人設定リポジトリである。

## ディレクトリ構成

```shell
.
├── plugins/
│   ├── trinity/                    # git submodule → https://github.com/yjn279/trinity
│   │                               #   Trinity プラグイン（Planner → Generator → Evaluator）
│   ├── code-review/                # subtree → anthropics/claude-plugins-official plugins/code-review
│   ├── code-simplifier/            # subtree → anthropics/claude-plugins-official plugins/code-simplifier
│   ├── claude-md-management/       # subtree → anthropics/claude-plugins-official plugins/claude-md-management
│   ├── feature-dev/                # subtree → anthropics/claude-plugins-official plugins/feature-dev
│   ├── frontend-design/            # subtree → anthropics/claude-plugins-official plugins/frontend-design
│   ├── plugin-dev/                 # subtree → anthropics/claude-plugins-official plugins/plugin-dev
│   ├── pr-review-toolkit/          # subtree → anthropics/claude-plugins-official plugins/pr-review-toolkit
│   └── ralph-loop/                 # subtree → anthropics/claude-plugins-official plugins/ralph-loop
├── scripts/
│   └── auto-resume/                # 使用量の上限で止まった会話を、解除の時刻に自動で再開する仕組み
│                                   #   → scripts/auto-resume/README.md
├── skills/
│   ├── humanizer/                  # git submodule → https://github.com/blader/humanizer
│   └── documentation/SKILL.md
├── settings.json               # 個人用フックと汎用 dev ツールの permissions
└── README.md
```

## ランタイム artifacts

`/trinity:run` は **実行プロジェクトのルート** に `.trinity/<run>/` を作って worktree とログを置く。`~/.claude/` 配下にはランタイム成果物を一切作らない。

`scripts/auto-resume/` の記録だけは `~/.claude/resume-logs/` と `~/.claude/auto-resume/` に置く。いずれも git の管理外である。

## 参考

- Claude Code: Explore the .claude directory — https://code.claude.com/docs/en/claude-directory
- Claude Code: Create plugins — https://code.claude.com/docs/en/plugins.md
- Claude Code: Sub agents — https://code.claude.com/docs/en/sub-agents
