"""60件規模の実例で、分割からテスト評価までの一連の数値の流れが破綻なく通ることを確認する。

言語モデルが担う段（規則の抽出・生成・判別）は対象外で、split.py と epoch.py の
出力だけで組み立てられる数値の流れだけを検証する。エポック数に上限は設けないため、
ここでは上限を扱わない。

python3 -m unittest discover -s skills/style-rubric/scripts で実行する。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import epoch  # noqa: E402
import split  # noqa: E402
from test_split import make_records  # noqa: E402

SEED = 1
DECEPTION_THRESHOLD = 0.6  # 見破られ率がこの値未満なら収束とみなす。


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


def build_batch(source_ids):
    """本人の文章の id 一覧から、本人と生成文が半々のバッチを組む。

    生成文は同じ文章から逆抽出した条件入力を使って作るため、本人側と生成文側は
    id を共有するが、どちらの役でも1つの id は1回しか登場しない。文章の使い回しは
    起きない。
    """
    batch = []
    for source_id in source_ids:
        batch.append({"source_id": source_id, "role": "本人"})
        batch.append({"source_id": source_id, "role": "生成文"})
    return batch


def make_verdicts(genuine_correct, genuine_wrong, fake_correct, fake_wrong):
    """混同行列の4区分の件数から、判別役の判定一覧を組み立てる。"""
    verdicts = []
    verdicts += [{"truth": "本人", "verdict": "本人"}] * genuine_correct
    verdicts += [{"truth": "本人", "verdict": "生成文"}] * genuine_wrong
    verdicts += [{"truth": "生成文", "verdict": "生成文"}] * fake_correct
    verdicts += [{"truth": "生成文", "verdict": "本人"}] * fake_wrong
    return verdicts


def balanced_convergent_verdicts(pair_count):
    """本人・生成文それぞれ pair_count 件からなる、見破られ率がちょうど0.5になる判定一覧を作る。

    分割から数の流れを通しで確かめるための値であり、閾値ちょうどの境界での
    収束判定そのものは PipelineEpochRecordTest が別途検証する。
    """
    half = pair_count // 2
    rest = pair_count - half
    return make_verdicts(
        genuine_correct=half, genuine_wrong=rest, fake_correct=half, fake_wrong=rest
    )


def epoch_record(epoch_no, verdicts):
    """1エポック分の判定一覧から、report.md が必要とする記録を組み立てる。

    集計そのものは epoch.py に委ね、ここではエポック番号を書き加えるだけである。
    判定が一方へ倒れていれば epoch.summarize が epoch.EpochError を送出し、
    収束判定へは進まない。
    """
    summary = epoch.summarize(verdicts)
    return {"epoch": epoch_no, **summary}


def is_converged(deception_rate):
    """見破られ率が閾値未満なら収束とみなす。"""
    return deception_rate < DECEPTION_THRESHOLD


class PipelineSplitTest(unittest.TestCase):
    def test_split_of_60_biased_records_covers_every_input_without_overlap(self):
        records = build_corpus(60)
        result = split.split_records(records, seed=SEED)

        all_assigned = [rid for ids in result["assignments"].values() for rid in ids]
        self.assertEqual(len(all_assigned), 60)
        self.assertEqual(len(all_assigned), len(set(all_assigned)))
        # 層ごとの丸めが積み重なるため厳密な7:2:1にはならないが、全件が
        # 過不足なくいずれか1つの集合に割り振られることを確かめる。
        self.assertEqual(sum(result["counts"].values()), 60)


class PipelineBatchTest(unittest.TestCase):
    def test_validation_set_forms_a_24_sample_batch_without_reusing_text(self):
        # 偏りのない60件は課題1で確認済みのとおり検証データが厳密に12件になる。
        # ここではその12件から24サンプルのバッチを使い回しなく組めることを確かめる。
        records = make_records(60)
        result = split.split_records(records, seed=SEED)
        validation_ids = result["assignments"]["validation"]
        self.assertEqual(len(validation_ids), 12)

        batch = build_batch(validation_ids)
        self.assertEqual(len(batch), 24)
        self.assertEqual(sum(1 for s in batch if s["role"] == "本人"), 12)
        self.assertEqual(sum(1 for s in batch if s["role"] == "生成文"), 12)

        for source_id in validation_ids:
            uses = [s for s in batch if s["source_id"] == source_id]
            self.assertEqual(len(uses), 2)
            self.assertEqual({s["role"] for s in uses}, {"本人", "生成文"})


class PipelineEpochRecordTest(unittest.TestCase):
    def test_epoch_record_contains_every_field_report_needs(self):
        verdicts = make_verdicts(genuine_correct=6, genuine_wrong=4, fake_correct=5, fake_wrong=5)
        record = epoch_record(1, verdicts)
        self.assertEqual(
            set(record),
            {"epoch", "total", "confusion", "deception_rate", "p_value", "genuine_answer_rate"},
        )

    def test_deception_rate_of_point_five_five_is_convergence(self):
        # 20件中11件正答で見破られ率0.55。
        verdicts = make_verdicts(genuine_correct=6, genuine_wrong=4, fake_correct=5, fake_wrong=5)
        record = epoch_record(1, verdicts)
        self.assertEqual(record["deception_rate"], 0.55)
        self.assertTrue(is_converged(record["deception_rate"]))

    def test_deception_rate_of_point_six_is_not_yet_convergence(self):
        # 20件中12件正答で見破られ率0.6。閾値は「未満」で収束のため、ちょうど0.6は収束しない。
        verdicts = make_verdicts(genuine_correct=6, genuine_wrong=4, fake_correct=6, fake_wrong=4)
        record = epoch_record(1, verdicts)
        self.assertEqual(record["deception_rate"], 0.6)
        self.assertFalse(is_converged(record["deception_rate"]))

    def test_deception_rate_of_point_seven_five_is_not_convergence(self):
        # 20件中15件正答で見破られ率0.75。
        verdicts = make_verdicts(genuine_correct=8, genuine_wrong=2, fake_correct=7, fake_wrong=3)
        record = epoch_record(1, verdicts)
        self.assertEqual(record["deception_rate"], 0.75)
        self.assertFalse(is_converged(record["deception_rate"]))

    def test_skewed_verdicts_stop_before_the_convergence_check(self):
        # 判別役が全サンプルに「生成文」と答えた退化ケース。収束判定へ進む前に停止する。
        verdicts = make_verdicts(genuine_correct=0, genuine_wrong=12, fake_correct=12, fake_wrong=0)
        with self.assertRaises(epoch.EpochError):
            epoch_record(1, verdicts)


class PipelineTestEvaluationTest(unittest.TestCase):
    def test_test_set_forms_a_12_sample_evaluation(self):
        records = make_records(60)
        result = split.split_records(records, seed=SEED)
        test_ids = result["assignments"]["test"]
        self.assertEqual(len(test_ids), 6)

        batch = build_batch(test_ids)
        self.assertEqual(len(batch), 12)

    def test_deception_rate_at_or_above_threshold_sends_back_to_rubric_generation(self):
        # テストデータでの見破られ率が閾値以上なら、ルーブリック生成へ戻る判断になる。
        verdicts = make_verdicts(genuine_correct=4, genuine_wrong=2, fake_correct=4, fake_wrong=2)
        result = epoch.summarize(verdicts)
        self.assertGreaterEqual(result["deception_rate"], DECEPTION_THRESHOLD)
        self.assertFalse(is_converged(result["deception_rate"]))


class PipelineFullFlowTest(unittest.TestCase):
    def test_flow_from_split_to_test_evaluation_runs_without_error(self):
        # 時期・長さ・話題が連動して偏った60件でも、分割からテスト評価までの
        # 数値の流れが例外なく通ることを確かめる。具体的な閾値の境界での
        # 収束判定は PipelineEpochRecordTest が別途検証しているので、ここでは
        # 見破られ率がちょうど0.5になる判定一覧を使い、流れの一貫性だけを見る。
        records = build_corpus(60)
        result = split.split_records(records, seed=SEED)
        validation_ids = result["assignments"]["validation"]
        test_ids = result["assignments"]["test"]

        validation_batch = build_batch(validation_ids)
        self.assertEqual(len(validation_batch), len(validation_ids) * 2)
        epoch_verdicts = balanced_convergent_verdicts(len(validation_ids))
        record = epoch_record(1, epoch_verdicts)
        self.assertEqual(set(record) - {"epoch"}, set(epoch.summarize(epoch_verdicts)))
        self.assertTrue(is_converged(record["deception_rate"]))

        test_batch = build_batch(test_ids)
        self.assertEqual(len(test_batch), len(test_ids) * 2)
        test_verdicts = balanced_convergent_verdicts(len(test_ids))
        test_result = epoch.summarize(test_verdicts)
        self.assertTrue(is_converged(test_result["deception_rate"]))


if __name__ == "__main__":
    unittest.main()
