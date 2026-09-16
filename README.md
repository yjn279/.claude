# personal `~/.claude/` config

このリポジトリは、そのまま `~/.claude/` の中身として動かす個人設定である。バージョン管理するのは設定・Skill・フックの実行ファイルだけで、Claude Code が実行時に作るデータは `.gitignore` で除外する。

## Structure

追跡しているファイルの構成を以下に示す。

```shell
.
├── .github/
│   └── dependabot.yml          # サブモジュールの更新 Pull Request を毎週立てる
├── skills/                     # Skill 群
├── scripts/
│   └── fable-advice/           # 会話が要約されたあと Fable に問いかけを求めるフックの実行ファイル
├── CLAUDE.md                   # すべてのプロジェクトに共通する指示
├── settings.json               # フック・権限・利用するプラグインの宣言
└── README.md
```

## Skills

`skills/` の各ディレクトリが 1 つの Skill に対応する。外部で配布されている Skill はサブモジュールとして取り込み、それ以外はこのリポジトリで直接管理する。

| Skill | 取得元 | 役割 |
| :-- | :-- | :-- |
| `frontend-slides` | zarazhangrui/frontend-slides | ブラウザだけで動くスライドを作る |
| `humanizer` | blader/humanizer | AI が書いたような文章を書き手の言葉へ直す |
| `git-flow` | このリポジトリ | ブランチ・worktree・Pull Request の運用 |
| `imagegen` | このリポジトリ | 画像の生成と編集 |
| `markdown` | このリポジトリ | Markdown とそれに準じた記法 |
| `product-management` | このリポジトリ | 価値提供の指標と、作らずに済ませる判断 |

## Plugins

プラグインは `settings.json` の `enabledPlugins` と `extraKnownMarketplaces` で宣言し、実体は Claude Code が `plugins/` へ取得する。したがって `plugins/` はバージョン管理しない。

## Runtime

`/trinity:run` は実行するプロジェクトのルートに `.trinity/<run>/` を作り、worktree とログをそこへ置く。`~/.claude/` 配下には実行時の成果物を作らない。

## References

- Claude Code: Explore the .claude directory — https://code.claude.com/docs/en/claude-directory
- Claude Code: Create plugins — https://code.claude.com/docs/en/plugins.md
- Claude Code: Sub agents — https://code.claude.com/docs/en/sub-agents
