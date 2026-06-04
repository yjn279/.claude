# personal `~/.claude/` config

このリポジトリは **そのまま `~/.claude/` の中身として動かす** ための個人設定リポジトリである。

## ディレクトリ構成

```shell
.
├── bin/
│   └── discord-channel.sh          # Discord チャネルリスナーの起動スクリプト
├── docs/
│   └── discord-channel.md          # Discord チャネル Bot のセットアップ手順
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
├── skills/
│   ├── humanizer/                  # git submodule → https://github.com/blader/humanizer
│   └── documentation/SKILL.md
├── settings.json               # 個人用フックと汎用 dev ツールの permissions
└── README.md
```

## ランタイム artifacts

`/trinity:run` は **実行プロジェクトのルート** に `.trinity/<run>/` を作って worktree とログを置く。`~/.claude/` 配下にはランタイム成果物を一切作らない。

## Discord channel

公式プラグイン `discord@claude-plugins-official` で Discord と Claude Code セッションを橋渡しする。起動は `bin/discord-channel.sh`、初期設定とアクセス制御の手順は [docs/discord-channel.md](docs/discord-channel.md) にまとめてある。トークンとアクセス設定（`channels/discord/`）はランタイムデータとして gitignore 済みで、リポジトリには含めない。

## 参考

- Claude Code: Explore the .claude directory — https://code.claude.com/docs/en/claude-directory
- Claude Code: Create plugins — https://code.claude.com/docs/en/plugins.md
- Claude Code: Sub agents — https://code.claude.com/docs/en/sub-agents
