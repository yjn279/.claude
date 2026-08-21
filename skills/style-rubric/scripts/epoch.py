#!/usr/bin/env python3
"""1エポック分の判定一覧から、混同行列・見破られ率・p 値を求める。

入力（標準入力または引数のファイルパスから読む JSON）:
    次のオブジェクトのリスト。
    - "truth"   （必須）正解。"本人" または "生成文"
    - "verdict" （必須）Discriminator の回答。"本人" または "生成文"

出力（標準出力への JSON、終了コード0）:
    - "total"               判定の総数
    - "confusion"           混同行列。正解（"genuine" = 本人 / "fake" = 生成文）を外側、
                             Discriminator の回答を内側のキーとする、4つの数の入れ子
    - "deception_rate"      見破られ率
    - "p_value"             見破られ率が50%と有意差なしという仮説のもとでの両側 p 値
    - "genuine_answer_rate" Discriminator が「本人」と答えた割合

前提が崩れている場合（判定一覧が空、truth/verdict が「本人」「生成文」以外、
「本人」と答えた割合が 0.3〜0.7 の範囲を外れているなど）は、理由を標準エラー出力へ書いて
終了コード1で異常終了する。
"""
from __future__ import annotations

import argparse
import json
import sys
from math import comb
from pathlib import Path

LABELS = ("本人", "生成文")
GENUINE_ANSWER_RATE_RANGE = (0.3, 0.7)


class EpochError(Exception):
    """判定一覧の集計の前提が崩れているときに送出する。"""


def _load_verdicts(path):
    """path が "-" なら標準入力から、それ以外ならファイルから JSON を読み込む。

    失敗すれば理由を標準エラー出力へ書いて None を返す。
    """
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"入力の読み込みに失敗しました: {exc}", file=sys.stderr)
        return None


def _label_key(label):
    return "genuine" if label == "本人" else "fake"


def _binomial_p_value(total, correct):
    """total 件中 correct 件正答のとき、正答率が50%と有意差なしという仮説のもとでの両側 p 値を返す。"""
    tail_start = max(correct, total - correct)
    tail = sum(comb(total, k) for k in range(tail_start, total + 1))
    return min(1.0, 2 * tail / (2 ** total))


def tally(verdicts):
    """判定一覧から混同行列を数え上げる。前提が崩れていれば EpochError を送出する。"""
    if not isinstance(verdicts, list) or not verdicts:
        raise EpochError("判定一覧は1件以上のリストである必要があります。")

    confusion = {"genuine": {"genuine": 0, "fake": 0}, "fake": {"genuine": 0, "fake": 0}}
    for i, sample in enumerate(verdicts):
        if not isinstance(sample, dict):
            raise EpochError(f"{i}件目は truth/verdict を持つオブジェクトである必要があります。")
        truth = sample.get("truth")
        verdict = sample.get("verdict")
        if truth not in LABELS or verdict not in LABELS:
            raise EpochError(
                f"{i}件目の truth/verdict は「本人」「生成文」のいずれかである必要があります"
                f"（truth: {truth!r}, verdict: {verdict!r}）。"
            )
        confusion[_label_key(truth)][_label_key(verdict)] += 1

    return confusion


def check_balance(confusion, total):
    """「本人」と答えた割合が 0.3〜0.7 の範囲にあるかを検査し、その割合を返す。

    範囲を外れていれば EpochError を送出する。
    """
    genuine_answers = confusion["genuine"]["genuine"] + confusion["fake"]["genuine"]
    genuine_answer_rate = genuine_answers / total
    low, high = GENUINE_ANSWER_RATE_RANGE
    if not (low <= genuine_answer_rate <= high):
        raise EpochError(
            "Discriminator の回答が一方へ倒れています。「本人」と答えた割合は"
            f"{genuine_answer_rate:.3f}で、許容範囲{low}〜{high}の外です。"
            "見破られ率は解釈できないため、判定を見直すか Discriminator のプロンプトを確認してください。"
        )
    return genuine_answer_rate


def summarize(verdicts):
    """判定一覧から混同行列・見破られ率・p 値・回答の内訳を求める。

    前提が崩れていれば EpochError を送出する。
    """
    confusion = tally(verdicts)
    total = len(verdicts)
    genuine_answer_rate = check_balance(confusion, total)

    correct = confusion["genuine"]["genuine"] + confusion["fake"]["fake"]
    deception_rate = correct / total
    p_value = _binomial_p_value(total, correct)

    return {
        "total": total,
        "confusion": confusion,
        "deception_rate": deception_rate,
        "p_value": p_value,
        "genuine_answer_rate": genuine_answer_rate,
    }


def main(argv):
    parser = argparse.ArgumentParser(
        description="1エポック分の判定一覧から、混同行列・見破られ率・p 値を求める。"
    )
    parser.add_argument(
        "input", nargs="?", default="-",
        help="入力 JSON ファイルのパス（省略または - で標準入力から読む）",
    )
    args = parser.parse_args(argv)

    verdicts = _load_verdicts(args.input)
    if verdicts is None:
        return 1

    try:
        result = summarize(verdicts)
    except EpochError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
