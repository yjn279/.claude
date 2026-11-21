#!/bin/sh
# 第1引数の名前にあいさつする
name="$1"
if [ -z "$name" ]; then
  echo "名前を渡してください" >&2
  exit 1
fi
echo "こんにちは、$name さん"
