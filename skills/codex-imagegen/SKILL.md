---
name: codex-imagegen
description: >-
  Codex CLI の内蔵 image_gen ツール（$imagegen）を呼び出して画像を生成・編集するスキル。
  「画像を作って／生成して」「この写真を編集して／背景を変えて／加工して／オブジェクトを消して」
  「ヒーロー画像・アイキャッチ・サムネ・バナー・イラスト・モックアップ・ロゴ案・商品写真・コンセプトアートが欲しい」
  「参照画像から別バリエーションを作って」など、ビットマップ画像の新規生成・既存画像の編集・参照画像からの
  バリエーション生成が必要なときは、ユーザーが明示的に「Codex」や「imagegen」と言わなくても必ずこのスキルを使う。
  Generate or edit raster images (photos, illustrations, mockups, textures, hero images, thumbnails,
  banners, logos, product shots, concept art) by driving the Codex CLI's built-in image_gen tool.
  Use it whenever the user wants to create, edit, transform, or make variants of an image or picture.
  Do NOT use it for SVG/vector icon systems, code-native diagrams, or visuals better built directly in HTML/CSS/canvas.
---

# Codex Imagegen

このスキルは、ローカルの Codex CLI が内蔵する image_gen ツール（プロンプト上では `$imagegen` と呼ばれる）を非対話モードで駆動し、画像の生成と編集を行う。Claude 自身は画像を描けないが、image_gen は GPT Image モデルで高品質なビットマップを生成・編集できるため、このスキルがその橋渡しを担う。生成と編集はどちらも image_gen という単一の仕組みで完結し、両者の違いは元画像を添付するか否かだけである。

## Prerequisites

実行には Codex CLI が必要で、次の2点を満たしていなければならない。

- `codex` CLI がインストール済みで PATH 上にあること（ `command -v codex` で確認できる）。
- Codex にログイン済みであること。内蔵 image_gen は `OPENAI_API_KEY` を必要とせず ChatGPT ログインで動作する。未ログインの場合は対話ログインが要るため、ユーザーにターミナルで `! codex login` の実行を依頼する。

## Core Tool

Codex の呼び出し、出力 PNG の特定、保存先へのコピーは、すべて同梱スクリプト `scripts/codex_image.sh` に集約してある。プロンプトを手で組み立てて `codex exec` を直接叩かず、このスクリプトを使う。そうすれば「image_gen を使え」「絶対パスを出力しろ」といった定型指示や、 `generated_images` からの出力探索を、呼び出しのたびに再発明せずに済む。スクリプトは成功すると最終行に必ず `IMAGE_PATH=<絶対パス>` を出力するので、この行から保存先を取得する。

呼び出し形式は生成と編集の2モードに分かれる。

```bash
# 生成
~/.claude/skills/codex-imagegen/scripts/codex_image.sh generate \
  --prompt "<画像の説明>" [--out <保存先.png>] [--cd <作業ディレクトリ>]

# 編集（元画像は絶対パスで指定）
~/.claude/skills/codex-imagegen/scripts/codex_image.sh edit \
  --src <元画像の絶対パス> --prompt "<編集の指示>" [--out <保存先.png>] [--cd <作業ディレクトリ>]
```

各フラグの用途を以下に示す。

| フラグ | 用途 |
| :-- | :-- |
| `--prompt` | 画像の説明（生成）または編集の指示（編集）。必須。 |
| `--src` | 編集対象の元画像。絶対パスで指定する。編集時のみ必須。 |
| `--out` | 最終的な保存先。省略時は `generated_images` 内のパスを返す。 |
| `--cd` | Codex の作業ルート。サンドボックスの読み取り範囲に影響する。 |

生成には通常 20〜60 秒かかる。スクリプトはバックグラウンドで実行し、出力に `IMAGE_PATH=` または `ERROR` が現れるまで待つ。

## Workflow

画像リクエストは次の手順で処理する。

1. 意図を判定する。既存画像を変える・一部を保つ要求なら編集、画像が無いか参照として渡されただけなら生成とする。迷う場合は生成を選ぶ。
2. プロンプトを練る（次節参照）。
3. スクリプトをバックグラウンドで実行し、 `IMAGE_PATH=` を待つ。
4. 結果を確認する。返ってきた PNG を Read ツールで読み込み、被写体・スタイル・構図・文字・編集の不変条件を目視で点検する。
5. 修正が要る場合は一度に1点だけ変えて再実行する。複数を同時に変えると原因の切り分けができなくなる。
6. 最終的な保存パスと使用プロンプトの要点をユーザーに報告する。

## Prompting

スクリプトが定型部分（image_gen の使用指示とパス出力）を補うため、呼び出し側は何を描く・どう変えるかに集中すればよい。良いプロンプトは「背景・状況 → 被写体 → ディテール → 制約」の順で具体的に記述する。ユーザーの指示がすでに具体的なら要素を足さず構造を整えるにとどめ、曖昧なときだけ品質が実際に向上する範囲で控えめに補う。頼まれていない登場人物・ブランド名・スローガン・配色は加えない。

用途に応じて次の点に注意する。

- 文字を入れる場合は、入れたい文字列を一字一句そのまま引用し、字体と配置も指定する。
- 編集の場合は不変条件を明示する（「背景だけ変える、被写体と輪郭は保つ」など）。スクリプトも保持を添えるが、重要な条件は自分のプロンプトでも繰り返す。
- アスペクト比やサイズは自然文で指定する（「横長 16:9」「正方形のサムネ」「縦長のポスター」など）。

より深いプロンプト設計、用途別テンプレート、透過背景の扱いは、Codex 同梱の一次情報 `~/.codex/skills/.system/imagegen/SKILL.md` を必要時に参照する。知識を重複させず、ここを唯一の出典として扱う。

## Output

内蔵モードでは画像は既定で `~/.codex/generated_images/<session>/ig_*.png` に保存される。用途に応じて保存先を決める。

- プレビューやブレスト目的なら、既定パスのまま Read で表示すればよく、コピーは不要。
- ユーザーが保存先を指定した場合やプロジェクトで使う成果物の場合は、 `--out` で保存先を渡す。スクリプトがそこへコピーし `IMAGE_PATH` をコピー先にする。プロジェクトで参照するアセットを既定パスだけに残さない。
- 既存ファイルは、ユーザーが置き換えを明言しない限り上書きせず、 `hero-v2.png` のような別名で保存する。

## Troubleshooting

代表的な不具合と対処を以下に示す。

| 現象 | 原因と対処 |
| :-- | :-- |
| 画像ができず `ERROR: no new image` が出る | モデルの拒否、ログイン切れ、サンドボックスの読み取りブロックなどが考えられる。スクリプトが表示する Codex の最終メッセージを読む。 |
| 編集で元画像が読めない | 元画像が作業ツリー外にあるとサンドボックスの制限に当たる。 `--cd` に元画像のあるディレクトリを渡すか、元画像を作業ディレクトリへ一時コピーする。 |
| 透過 PNG が欲しい | 内蔵モードは真の透過を直接出せない。単純な被写体ならクロマキー背景で生成し `remove_chroma_key.py` で抜く。本物の透過が要る場合は `OPENAI_API_KEY` を使う CLI フォールバックが必要で、ユーザーに確認してから実行する。 |
| CLI/API/モデルを明示指定したい | 既定の内蔵モードで十分なため通常は不要。明示要求があるときだけ Codex 同梱の `references/cli.md` を参照する。 |

## Examples

生成と編集の典型的な呼び出し例を示す。

### Generation

```bash
~/.claude/skills/codex-imagegen/scripts/codex_image.sh generate \
  --prompt "ミニマルな陶器のコーヒーマグのヒーロー画像。クリーンな商品写真、柔らかいスタジオ照明、横長のワイド構図でコピー用の余白を左に確保。ロゴや文字は入れない。" \
  --out ./assets/hero-mug.png
```

### Editing

```bash
~/.claude/skills/codex-imagegen/scripts/codex_image.sh edit \
  --src /Users/me/photos/product.png \
  --prompt "背景だけ暖色の夕焼けグラデーションに置き換える。被写体の商品とその輪郭はそのまま保つ。文字やウォーターマークは入れない。" \
  --out ./assets/product-sunset.png
```
