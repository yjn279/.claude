#!/usr/bin/env python3
"""1エポック分の判定一覧から、混同行列・見破られ率・p 値を求める。

Discriminator（見本を参照し、提示された1件の文章が本人の筆か生成文かを判定する言語モデル
呼び出し）は、本人の文章と生成文を半々に混ぜたバッチを1サンプルずつ判定する。その判定一覧
（各サンプルの正解が本人か生成文か、Discriminator が本人と答えたか生成文と答えたか）を受け取り、
混同行列を数え上げたうえで、見破られ率（Discriminator の正答率）と、その正答率が偶然（50%）と
有意差があるかを示す p 値を binomial.py の計算で求める。見破られ率が 0.5 に近いほど、
生成文と本人の文章が区別できなくなっていることを表す代理指標である。計算そのものは
binomial.py にしかなく、ここでは二重に持たない。

このスクリプトはあわせて、判定結果が一方へ倒れていないかを検査する。半々のバッチで
Discriminator が中身を見ずに全部「生成文」と答えるだけでも見破られ率はちょうど 0.5 になってしまう、
1サンプルずつ独立に判定する形に固有の退化がある。これを塞ぐため、「本人」と答えた割合が
0.3〜0.7 の範囲（両端を含む）を外れていないかを検査し、外れていれば代替値で続行せず
理由を示して異常終了する。これは条件分岐ではなくアサーションである。

入力（標準入力または引数のファイルパスから読む JSON）:
    次のオブジェクトのリスト。
    - "truth"   （必須）正解。"本人" または "生成文"
    - "verdict" （必須）Discriminator の回答。"本人" または "生成文"

出力（標準出力への JSON、終了コード0）:
    - "total"               判定の総数
    - "confusion"           混同行列。正解（"genuine" = 本人 / "fake" = 生成文）を外側、
                             Discriminator の回答を内側のキーとする、4つの数の入れ子
    - "deception_rate"      見破られ率（Discriminator の正答率）
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import binomial  # noqa: E402
import cli_io  # noqa: E402

LABELS = ("本人", "生成文")
GENUINE_ANSWER_RATE_RANGE = (0.3, 0.7)


class EpochError(Exception):
    """判定一覧の集計の前提が崩れているときに送出する。"""


def _label_key(label):
    return "genuine" if label == "本人" else "fake"


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
    deception_rate, p_value = binomial.binomial_test(total, correct)

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

    verdicts = cli_io.load_json_or_report(args.input)
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
