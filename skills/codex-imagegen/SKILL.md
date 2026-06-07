---
name: codex-imagegen
description: Generate or edit images via the Codex CLI. Use whenever the user wants to create, edit, or vary an image or picture, not for SVG/vector or diagrams.
---

# Codex Imagegen

Claude 自身は画像を描けないが、ローカルの Codex CLI は内蔵の imagegen スキルで高品質な画像を生成・編集できる。このスキルは、その Codex を `codex exec` で非対話的に呼び出すための橋渡しである。Codex は自律エージェントなので、こちらは作りたい画像を自然文で頼むだけでよい。出力の探索や定型処理を作り込む必要はなく、保存先は Codex 自身が応答で報告する。

## Prerequisites

実行には Codex CLI が要る。次の2点を満たすこと。

- `codex` が PATH 上にある（ `command -v codex` で確認）。
- Codex にログイン済み。内蔵 imagegen は `OPENAI_API_KEY` 不要で ChatGPT ログインで動く。未ログインならユーザーに `! codex login` を依頼する。

## Usage

`codex exec` に、imagegen スキルを使う指示と作りたい画像の説明を渡す。生成と編集の違いは、元画像を `-i` で添付するかどうかだけである。生成には 20〜60 秒かかるため Bash はバックグラウンドで実行し、Codex の応答に保存先パスが現れるまで待つ。

生成:

```bash
codex exec --skip-git-repo-check \
  "imagegen スキルで画像を1枚生成して。<作りたい画像の説明>。保存した絶対パスを最後の行に出力して。"
```

編集（元画像は絶対パスで渡す。`-i` は可変長なので、必ずプロンプトを先・ `-i` を最後に置く）:

```bash
codex exec --skip-git-repo-check \
  "添付画像を imagegen スキルで編集して。<変更内容>。変更点以外はそのまま保ち、新しいファイルとして保存して、絶対パスを最後の行に出力して。" \
  -i <元画像の絶対パス>
```

Codex は既定で `~/.codex/generated_images/<session>/` に PNG を保存する。応答にパスが見当たらないときは、そのディレクトリの最新ファイルを見ればよい。

## Workflow

画像リクエストは次の手順で処理する。

1. 生成か編集かを判断する。既存画像を変える要求なら編集、無ければ生成。迷えば生成。
2. 上記コマンドを実行し、応答から保存先パスを得る。
3. その PNG を Read で開き、被写体・構図・文字・編集の不変条件を目視で確認する。
4. 直しが要るなら一度に1点だけ変えて再実行する。複数同時に変えると原因の切り分けができない。
5. 保存先のパスをユーザーに報告する。永続的に使う成果物なら、目的の場所へ `cp` で移す。

## Prompting

良いプロンプトは「背景・状況 → 被写体 → ディテール → 制約」の順で具体的に書く。文字を入れるなら入れたい文字列を一字一句そのまま引用し、編集なら保ちたい不変条件を明示する。頼まれていない登場人物・ブランド名・配色は足さない。用途別テンプレートや透過背景の扱いなど踏み込んだ設計は、Codex 同梱の一次情報 `~/.codex/skills/.system/imagegen/SKILL.md` を必要時に参照する。
