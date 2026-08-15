#!/usr/bin/env python3
"""本人の文章を Y_train / Y_ref / Y_val / Y_test の4集合へ層化して振り分ける。

集合の役割:
- Y_train（約40%） 規則の抽出と更新に使う
- Y_ref （約20%） 判別役に見せる、書き手の見本
- Y_val （約25%） 反復のなかでの評価に使う本人側サンプル
- Y_test（約15%） 収束後の最終検証専用。反復中は一度も参照しない

時期・長さ・話題の偏りが各集合へ均等に散るよう、この3項目を組み合わせた層ごとに
比率どおりの人数を割り当てる。長さは文章の文字数から、時期は日付から、この
スクリプトが自動で求める。話題だけは文章そのものから機械的に決まらないため、
呼び出し側が1件ごとに札（ラベル）を添える。

入力（標準入力または引数のファイルパスから読む JSON）:
    次のオブジェクトのリスト。
    - "id"   （必須）文章を一意に識別する文字列
    - "text" （必須）書きぶりと関係のない定型部分を除いたあとの本文
    - "date" （任意）"YYYY-MM-DD" 形式の日付。時期の層に使う
    - "topic"（任意）話題を表す短い札。一部の文章にだけ付けることはできない

出力（標準出力への JSON、終了コード0）:
    - "seed"        振り分けに使った乱数の種
    - "total"       入力の件数
    - "counts"      集合ごとの件数
    - "strata"      層ごとの内訳（層の構成・件数・集合ごとの件数）
    - "assignments" 集合ごとに振り分けられた id の一覧

前提が崩れている場合（30件未満の入力、話題の札が一部だけ付いている入力など）は、
理由を標準エラー出力へ書いて終了コード1で異常終了する。
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date

SET_NAMES = ("Y_train", "Y_ref", "Y_val", "Y_test")
SET_RATIOS = (0.40, 0.20, 0.25, 0.15)
MIN_RECORDS_FOR_ITERATION = 30
BUCKET_COUNT = 3  # 時期・長さをそれぞれ何段階に分けるか


class SplitError(Exception):
    """振り分けの前提が崩れているときに送出する。"""


def _validate_records(records):
    if not isinstance(records, list):
        raise SplitError("入力は文章オブジェクトのリストである必要があります。")

    if len(records) < MIN_RECORDS_FOR_ITERATION:
        raise SplitError(
            f"入力が{len(records)}件です。30件を下回るため統計的な収束判定は成立しません。"
            "反復と検定は行わず、規則の記述だけを作る定性モードに切り替えてください。"
        )

    seen_ids = set()
    for record in records:
        if "id" not in record or "text" not in record:
            raise SplitError("各文章には id と text が必要です。")
        rid = record["id"]
        if rid in seen_ids:
            raise SplitError(f"id が重複しています: {rid!r}")
        seen_ids.add(rid)

    has_topic = [bool(r.get("topic")) for r in records]
    if any(has_topic) and not all(has_topic):
        with_topic = sum(has_topic)
        raise SplitError(
            "話題の札が一部の文章にしか付いていません"
            f"（付与 {with_topic} 件 / 未付与 {len(records) - with_topic} 件）。"
            "全件に付けるか、全件から外してください。"
        )


def _rank_buckets(values, bucket_count):
    """値の小さい順に並べ、件数が均等になるよう bucket_count 段階に分ける。"""
    order = sorted(values, key=lambda k: (values[k], k))
    n = len(order)
    return {key: (idx * bucket_count // n) for idx, key in enumerate(order)}


def _stratum_keys(records):
    lengths = {r["id"]: len(r["text"]) for r in records}
    length_bucket = _rank_buckets(lengths, BUCKET_COUNT)

    dated = {}
    for r in records:
        raw_date = r.get("date")
        if not raw_date:
            continue
        try:
            dated[r["id"]] = date.fromisoformat(raw_date).toordinal()
        except ValueError as exc:
            raise SplitError(f"日付の形式が不正です: {r['id']!r} -> {raw_date!r}") from exc
    period_bucket = _rank_buckets(dated, BUCKET_COUNT) if dated else {}

    keys = {}
    for r in records:
        rid = r["id"]
        period_label = f"period{period_bucket[rid]}" if rid in period_bucket else None
        length_label = f"length{length_bucket[rid]}"
        topic_label = r.get("topic") or None
        keys[rid] = (period_label, length_label, topic_label)
    return keys


def _allocate(n):
    """n 件を SET_RATIOS の比率で4集合へ分ける件数を、最大剰余法で求める。"""
    exact = [n * ratio for ratio in SET_RATIOS]
    base = [int(x) for x in exact]
    remainder = n - sum(base)
    order = sorted(range(len(SET_RATIOS)), key=lambda i: (-(exact[i] - base[i]), i))
    for i in range(remainder):
        base[order[i]] += 1
    return base


def split_records(records, seed):
    """振り分けを実行し、出力用の辞書を返す。前提が崩れていれば SplitError を送出する。"""
    _validate_records(records)
    keys = _stratum_keys(records)

    groups = {}
    for r in records:
        groups.setdefault(keys[r["id"]], []).append(r["id"])

    rng = random.Random(seed)
    assignments = {name: [] for name in SET_NAMES}
    strata_summary = []
    for key in sorted(groups, key=lambda k: (k[0] or "", k[1], k[2] or "")):
        ids = sorted(groups[key])
        rng.shuffle(ids)
        counts = _allocate(len(ids))

        idx = 0
        stratum_counts = {}
        for name, c in zip(SET_NAMES, counts):
            assignments[name].extend(ids[idx: idx + c])
            stratum_counts[name] = c
            idx += c

        period_label, length_label, topic_label = key
        strata_summary.append({
            "key": {
                "period": period_label,
                "length": length_label,
                "topic": topic_label,
            },
            "size": len(ids),
            "counts": stratum_counts,
        })

    return {
        "seed": seed,
        "total": len(records),
        "counts": {name: len(assignments[name]) for name in SET_NAMES},
        "strata": strata_summary,
        "assignments": assignments,
    }


def main(argv):
    parser = argparse.ArgumentParser(
        description="本人の文章を Y_train / Y_ref / Y_val / Y_test の4集合へ層化して振り分ける。"
    )
    parser.add_argument(
        "input", nargs="?", default="-",
        help="入力 JSON ファイルのパス（省略または - で標準入力から読む）",
    )
    parser.add_argument("--seed", type=int, required=True, help="振り分けに使う乱数の種")
    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            with open(args.input, encoding="utf-8") as f:
                raw = f.read()
        records = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"入力の読み込みに失敗しました: {exc}", file=sys.stderr)
        return 1

    try:
        result = split_records(records, args.seed)
    except SplitError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
