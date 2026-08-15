"""60件規模の実例で、振り分け・ラウンド記録・収束判定・最終検証という
一連の数値の流れが破綻なく通ることを確認する。
言語モデルが担う段（規則の抽出・生成・判別）は対象外で、
split.py と binomial.py の出力だけで組み立てられる数値の流れだけを検証する。

python3 -m unittest discover -s skills/style-rubric/scripts で実行する。
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import binomial  # noqa: E402
import split  # noqa: E402
from test_split import make_records  # noqa: E402

SEED = 1
MAX_ROUNDS = 8
MIN_PAIRS_PER_ROUND = 20
CONVERGENCE_STREAK = 2
P_THRESHOLD = 0.05


def build_corpus(n=60):
    """時期・長さ・話題のいずれにも偏りがある n 件の模擬入力を組み立てる。

    前半を話題A・古い時期・短い文章、後半を話題B・新しい時期・長い文章にそろえ、
    三つの偏りが連動する現実的な60件規模の入力を模す。
    """
    def topic_of(i):
        return "A" if i < n * 2 // 3 else "B"

    def date_of(i):
        year = 2020 if i < n * 2 // 3 else 2024
        month = (i % 12) + 1
        return f"{year}-{month:02d}-01"

    def length_of(i):
        return 20 if i < n * 2 // 3 else 200

    return make_records(n, topic_of=topic_of, date_of=date_of, length_of=length_of)


def round_record(round_no, total, correct):
    """1ラウンド分の記録を組み立てる。report.md が必要とする項目をすべて含む。"""
    rate, p_value = binomial.binomial_test(total, correct)
    insignificant = p_value > P_THRESHOLD
    return {
        "round": round_no,
        "total": total,
        "correct": correct,
        "rate": rate,
        "p_value": p_value,
        "judgment": "収束の目安を満たす" if insignificant else "収束の目安に届かず",
    }


def is_convergence_candidate(round_records):
    """直近 CONVERGENCE_STREAK ラウンド連続で「50%と有意差なし」なら収束候補とする。"""
    if len(round_records) < CONVERGENCE_STREAK:
        return False
    return all(r["p_value"] > P_THRESHOLD for r in round_records[-CONVERGENCE_STREAK:])


def final_check_record(total, correct):
    """Y_test による最終検証の記録を組み立てる。"""
    rate, p_value = binomial.binomial_test(total, correct)
    converged = p_value > P_THRESHOLD
    return {
        "total": total,
        "correct": correct,
        "rate": rate,
        "p_value": p_value,
        "judgment": (
            "最終検証を通過し収束"
            if converged
            else "評価用の集合への合わせ込みの疑いがあり反復へ戻る"
        ),
    }


class PipelineSplitTest(unittest.TestCase):
    def test_split_of_60_biased_records_covers_every_input_without_overlap(self):
        records = build_corpus(60)
        result = split.split_records(records, seed=SEED)

        all_assigned = [rid for ids in result["assignments"].values() for rid in ids]
        self.assertEqual(len(all_assigned), 60)
        self.assertEqual(len(all_assigned), len(set(all_assigned)))
        # 分割自体は課題1で確認済みだが、後続のラウンド記録・収束判定が
        # 実際の分割結果の上に成り立つことを、通しでここでも確かめる。
        self.assertEqual(
            result["counts"],
            {"Y_train": 24, "Y_ref": 12, "Y_val": 15, "Y_test": 9},
        )

    def test_val_set_can_supply_a_round_of_20_or_more_pairs(self):
        records = build_corpus(60)
        result = split.split_records(records, seed=SEED)
        y_val = result["assignments"]["Y_val"]
        self.assertGreater(len(y_val), 0)

        # Y_val の件数（15件）は1ラウンドに必要な20組を下回るが、
        # 同じ文章を複数回使えば20組以上を組める。
        # ただし特定の1件だけが使い回されないよう、使用回数の上限を確認する。
        selections = [y_val[i % len(y_val)] for i in range(MIN_PAIRS_PER_ROUND)]
        self.assertEqual(len(selections), MIN_PAIRS_PER_ROUND)
        usage = Counter(selections)
        max_allowed_reuse = -(-MIN_PAIRS_PER_ROUND // len(y_val))  # 切り上げ除算
        self.assertLessEqual(max(usage.values()), max_allowed_reuse)


class PipelineRoundRecordTest(unittest.TestCase):
    def test_round_record_contains_every_field_report_needs(self):
        record = round_record(1, total=20, correct=10)
        self.assertEqual(
            set(record), {"round", "total", "correct", "rate", "p_value", "judgment"}
        )

    def test_two_consecutive_insignificant_rounds_are_a_convergence_candidate(self):
        records = [
            round_record(1, total=20, correct=10),
            round_record(2, total=20, correct=11),
        ]
        self.assertTrue(all(r["p_value"] > P_THRESHOLD for r in records))
        self.assertTrue(is_convergence_candidate(records))

    def test_single_insignificant_round_is_not_yet_a_candidate(self):
        records = [round_record(1, total=20, correct=10)]
        self.assertFalse(is_convergence_candidate(records))

    def test_a_significant_round_breaks_the_streak(self):
        records = [
            round_record(1, total=20, correct=10),
            round_record(2, total=20, correct=15),  # p<0.05 で有意
        ]
        self.assertLess(records[1]["p_value"], P_THRESHOLD)
        self.assertFalse(is_convergence_candidate(records))


class PipelineFinalCheckTest(unittest.TestCase):
    def test_final_check_with_skewed_result_sends_back_to_iteration(self):
        records = build_corpus(60)
        result = split.split_records(records, seed=SEED)
        y_test_count = result["counts"]["Y_test"]

        # Y_test の全件を見破られた想定（評価用の集合に合わせ込んでいた場合の典型例）。
        final = final_check_record(total=y_test_count, correct=y_test_count)
        self.assertLess(final["p_value"], P_THRESHOLD)
        self.assertIn("反復へ戻る", final["judgment"])

    def test_final_check_with_chance_level_result_confirms_convergence(self):
        final = final_check_record(total=20, correct=10)
        self.assertGreater(final["p_value"], P_THRESHOLD)
        self.assertIn("収束", final["judgment"])


class PipelineCutoffTest(unittest.TestCase):
    def test_eight_rounds_without_convergence_triggers_cutoff(self):
        records = []
        for round_no in range(1, MAX_ROUNDS + 1):
            records.append(round_record(round_no, total=20, correct=15))  # 常に有意
            self.assertFalse(is_convergence_candidate(records))

        self.assertEqual(len(records), MAX_ROUNDS)
        cutoff_reached = len(records) >= MAX_ROUNDS and not is_convergence_candidate(records)
        self.assertTrue(cutoff_reached)


if __name__ == "__main__":
    unittest.main()
