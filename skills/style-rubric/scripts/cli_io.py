#!/usr/bin/env python3
"""標準入力または引数のファイルパスから JSON を読み込む、CLI 共通の入力処理。"""
from __future__ import annotations

import json
import sys


def read_json_input(path):
    """path が "-" なら標準入力から、それ以外なら path のファイルから読み込み、JSON としてパースする。

    読み込みまたはパースに失敗すれば OSError または json.JSONDecodeError を送出する。
    """
    if path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    return json.loads(raw)


def load_json_or_report(path):
    """read_json_input を呼び、失敗すれば理由を標準エラー出力へ書いて None を返す。

    呼び出し側は None を、終了コード1で異常終了する合図として扱う。
    """
    try:
        return read_json_input(path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"入力の読み込みに失敗しました: {exc}", file=sys.stderr)
        return None
