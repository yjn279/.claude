#!/bin/sh
# サンプルで検証と書き出しを通す。一時フォルダに小さな git リポジトリを作り、その中のコミットを指す tree.json を生成して使う。
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
cp "$HERE"/repo/* "$WORK"/
git -C "$WORK" init -q
git -C "$WORK" add .
git -C "$WORK" -c user.name=sample -c user.email= commit -q -m sample
SHA=$(git -C "$WORK" rev-parse HEAD)
sed "s/__SHA__/$SHA/g" "$HERE/tree.json" > "$WORK.json"
python3 "$HERE/../validate.py" "$WORK.json" "$WORK"
python3 "$HERE/../build.py" "$WORK.json" "$WORK" "$WORK.html"
