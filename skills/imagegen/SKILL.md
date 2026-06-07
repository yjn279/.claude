---
name: imagegen
description: Generate or edit images via the Codex CLI. Use whenever the user wants to create, edit, or vary an image or picture, not for SVG/vector or diagrams.
---

# Imagegen

Claude 自身は画像を描けないが、ローカルの Codex CLI は内蔵の imagegen スキルで高品質な画像を生成・編集できる。このスキルは、その Codex を `codex exec` で非対話的に呼び出すための橋渡しである。Codex は自律エージェントなので、こちらは作りたい画像を自然文で頼むだけでよい。

## Prerequisites

Codex CLI がインストール済みかつログイン済みなら動く。都度の事前確認は過剰なので行わず、コマンドが正常に動かないときだけ次を確認する。

- `codex` が PATH 上にあるか。
- Codex にログイン済みか。内蔵 imagegen は `OPENAI_API_KEY` 不要で ChatGPT ログインで動く。未ログインならユーザーに `! codex login` を依頼する。

## Usage

`codex exec` に `$imagegen <プロンプト>` を渡す。生成と編集の違いは、元画像を `-i` で添付するかどうかだけである。`$` を bash に展開させないよう、プロンプトはシングルクォートで囲む。生成には 20〜60 秒かかるため、Bash はバックグラウンドで実行する。

```bash
# 生成
codex exec --skip-git-repo-check '$imagegen <プロンプト>'

# 編集（元画像は絶対パス。-i は可変長なので、必ずプロンプトを先・ -i を最後に置く）
codex exec --skip-git-repo-check '$imagegen <プロンプト>' -i <元画像の絶対パス>
```

Codex は生成した PNG を `~/.codex/generated_images/<session>/` に保存する。最新のファイルが成果物なので、Read で開いて確認する。

## Prompting

プロンプト設計は、Codex 同梱の `~/.codex/skills/.system/imagegen/SKILL.md` を参照する。
