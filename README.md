# personal `~/.claude/` config

このリポジトリは、そのまま `~/.claude/` の中身として動かす個人設定である。バージョン管理するのは設定・Skill・フックの実行ファイルだけで、Claude Code が実行時に作るデータは `.gitignore` で除外する。

## Structure

追跡しているファイルの構成を以下に示す。

```shell
.
├── .github/
│   └── dependabot.yml          # サブモジュールの更新 Pull Request を毎週立てる
├── skills/                     # Skill 群と、このリポジトリで作るプラグイン
├── scripts/
│   ├── auto-resume/            # 使用量の上限で止まった会話を、解除の時刻に自動で再開するフックの実行ファイル
│   ├── fable-advice/           # manage Skill でサブエージェントが報告を返した後に Fable へ問いかけを求めるフックの実行ファイル
│   ├── language-drift/         # 応答の言語のずれを見つけて言い直させるフックの実行ファイル
│   ├── report-gaps/            # 報告に欠けた前提・結論を見つけて言い直させるフックの実行ファイル
│   └── reply-verdict.mjs       # language-drift と report-gaps が使う、応答への判定を Haiku から受け取る処理
├── CLAUDE.md                   # すべてのプロジェクトに共通する指示
├── settings.json               # フック・権限・利用するプラグインの宣言
└── README.md
```

## Skills

`skills/` の各ディレクトリは、1 つの Skill か、このリポジトリで作るプラグインに対応する。プラグインは Plugins 節で扱う。外部で配布されている Skill はサブモジュールとして取り込み、それ以外はこのリポジトリで直接管理する。Claude のアプリや Orca・Ego などのツールが自分で配置して更新する Skill は `.gitignore` で除外し、バージョン管理しない。

| Skill | 取得元 | 役割 |
| :-- | :-- | :-- |
| `humanizer` | blader/humanizer | AI が書いたような文章を書き手の言葉へ直す |
| `git-flow` | このリポジトリ | ブランチ・worktree・Pull Request の運用 |
| `imagegen` | このリポジトリ | 画像の生成と編集 |
| `manage` | このリポジトリ | メインエージェントを管理役に徹させ、実務をサブエージェントへ任せる |
| `markdown` | このリポジトリ | Markdown とそれに準じた記法 |
| `product-management` | このリポジトリ | 価値提供の指標と、作らずに済ませる判断 |

## Plugins

プラグインは取得元によって管理の仕方が分かれる。外部のプラグインは `settings.json` の `enabledPlugins` と `extraKnownMarketplaces` で宣言し、実体は Claude Code が `plugins/` へ取得する。したがって `plugins/` はバージョン管理しない。

このリポジトリで作るプラグインは `skills/<name>/` に `.claude-plugin/` を置いて管理する。Claude Code はこれを `settings.json` での宣言なしに読み込む。

| Plugin | 役割 |
| :-- | :-- |
| `idle-compact` | 最後のターンから `54` 分（プロンプトキャッシュの有効期間 `1` 時間の `90%` ）が過ぎたとき、会話が `10` 万トークン以上あれば圧縮する |

## Runtime

`/trinity:run` は実行するプロジェクトのルートに `.trinity/<run>/` を作り、worktree とログをそこへ置き、`~/.claude/` 配下には実行時の成果物を作らない。

`scripts/auto-resume/` は、判定と再開の記録を `~/.claude/resume-logs/` に、会話ごとの再開の状態を `~/.claude/auto-resume/` に置く。いずれもバージョン管理しない。

## References

- Claude Code: Explore the .claude directory — https://code.claude.com/docs/en/claude-directory
- Claude Code: Create plugins — https://code.claude.com/docs/en/plugins.md
- Claude Code: Sub agents — https://code.claude.com/docs/en/sub-agents
