#!/usr/bin/env python3
"""判定の総数と正答数から、正答率と二項検定の p 値を求める。

判別役が本人の文章を当てられた回数（正答数）と判定の総数を受け取り、
正答率が「当てずっぽう（50%）と有意差なし」と言えるかどうかを両側二項検定で調べる。
判別役の実力確認（正答率 0.8 以上を要求）にも、反復の収束判定
（p 値が 0.05 を上回る状態が続くか）にも、このスクリプトの出力だけを根拠にする。
しきい値による合否の判断はこのスクリプトでは行わず、呼び出し側に委ねる。

入力（コマンドライン引数）:
    --total   （必須）判定の総数
    --correct （必須）判別役が正しく本人の文章を当てた回数

出力（標準出力への JSON 1行、終了コード0）:
    - "total"    判定の総数
    - "correct"  正答数
    - "rate"     正答率（correct / total）
    - "p_value"  正答率が50%と有意差なしという仮説のもとでの両側 p 値

前提が崩れている場合（総数が0以下、正答数が負または総数を超えるなど）は、
理由を標準エラー出力へ書いて終了コード1で異常終了する。
"""
from __future__ import annotations

import argparse
import json
import sys
from math import comb


class BinomialTestError(Exception):
    """検定の前提が崩れているときに送出する。"""


def binomial_test(total, correct):
    """正答率と、50%からの食い違いが偶然の範囲かを表す両側 p 値を返す。

    前提が崩れていれば BinomialTestError を送出する。
    """
    if total <= 0:
        raise BinomialTestError("総数は1以上である必要があります。")
    if correct < 0 or correct > total:
        raise BinomialTestError(
            f"正答数は0以上{total}以下である必要があります（正答数: {correct}）。"
        )

    rate = correct / total

    # 50% を中心とした対称な分布のもとで、観測値より極端な側（大きい方の数え）の
    # 裾を求め、その2倍を p 値とする。正答数と外れ数のどちらを渡しても
    # 大きい方が同じ裾になるため、両者を入れ替えても値は変わらない。
    tail_start = max(correct, total - correct)
    tail = sum(comb(total, k) for k in range(tail_start, total + 1))
    p_value = min(1.0, 2 * tail / (2 ** total))

    return rate, p_value


def main(argv):
    parser = argparse.ArgumentParser(
        description="判定の総数と正答数から、正答率と二項検定の p 値を求める。"
    )
    parser.add_argument("--total", type=int, required=True, help="判定の総数")
    parser.add_argument("--correct", type=int, required=True, help="正答数")
    args = parser.parse_args(argv)

    try:
        rate, p_value = binomial_test(args.total, args.correct)
    except BinomialTestError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = {
        "total": args.total,
        "correct": args.correct,
        "rate": rate,
        "p_value": p_value,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
