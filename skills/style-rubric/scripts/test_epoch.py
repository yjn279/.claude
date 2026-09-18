"""epoch.py のテスト。python3 -m unittest discover -s skills/style-rubric/scripts で実行する。"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import epoch  # noqa: E402
import split  # noqa: E402
from test_split import make_records  # noqa: E402

SEED = 1
DECEPTION_THRESHOLD = 0.6  # 見破られ率がこの値未満なら収束とみなす。


def run_main(main_func, argv):
    """main_func(argv) を呼び、(戻り値, 標準出力, 標準エラー出力) を返す。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main_func(argv)
    return code, out.getvalue(), err.getvalue()


def run_subprocess(script_path, args, stdin=None):
    """script_path を別プロセスとして実行し、subprocess.CompletedProcess を返す。"""
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def make_verdicts(genuine_correct, genuine_wrong, fake_correct, fake_wrong):
    """混同行列の4区分の件数から判定一覧を組み立てる。

    genuine_correct: 正解が本人で、Discriminator も本人と答えた件数
    genuine_wrong:    正解が本人だが、Discriminator は生成文と答えた件数
    fake_correct:     正解が生成文で、Discriminator も生成文と答えた件数
    fake_wrong:       正解が生成文だが、Discriminator は本人と答えた件数
    """
    verdicts = []
    verdicts += [{"truth": "本人", "verdict": "本人"}] * genuine_correct
    verdicts += [{"truth": "本人", "verdict": "生成文"}] * genuine_wrong
    verdicts += [{"truth": "生成文", "verdict": "生成文"}] * fake_correct
    verdicts += [{"truth": "生成文", "verdict": "本人"}] * fake_wrong
    return verdicts


def build_batch(source_ids):
    """本人の文章の id 一覧から、本人と生成文が半々のバッチを組む。"""
    batch = []
    for source_id in source_ids:
        batch.append({"source_id": source_id, "role": "本人"})
        batch.append({"source_id": source_id, "role": "生成文"})
    return batch


class EpochSummarizeTest(unittest.TestCase):
    def test_24_samples_produce_confusion_rate_and_p_value(self):
        # 検証データ12件から本人12・生成文12の24サンプルのバッチを想定する。
        verdicts = make_verdicts(genuine_correct=9, genuine_wrong=3, fake_correct=8, fake_wrong=4)
        result = epoch.summarize(verdicts)

        self.assertEqual(result["total"], 24)
        self.assertIn("confusion", result)
        self.assertIn("deception_rate", result)
        self.assertIn("p_value", result)

    def test_confusion_counts_sum_to_total(self):
        verdicts = make_verdicts(genuine_correct=9, genuine_wrong=3, fake_correct=8, fake_wrong=4)
        result = epoch.summarize(verdicts)

        confusion = result["confusion"]
        total_from_confusion = sum(
            confusion[truth][verdict] for truth in confusion for verdict in confusion[truth]
        )
        self.assertEqual(total_from_confusion, result["total"])

    def test_deception_rate_is_correct_predictions_over_total(self):
        verdicts = make_verdicts(genuine_correct=9, genuine_wrong=3, fake_correct=8, fake_wrong=4)
        result = epoch.summarize(verdicts)

        correct = result["confusion"]["genuine"]["genuine"] + result["confusion"]["fake"]["fake"]
        self.assertEqual(result["deception_rate"], correct / result["total"])

    def test_empty_input_is_rejected(self):
        with self.assertRaises(epoch.EpochError):
            epoch.summarize([])

    def test_unknown_label_is_rejected(self):
        with self.assertRaises(epoch.EpochError):
            epoch.summarize([{"truth": "本人", "verdict": "不明"}])

    def test_non_dict_entry_is_rejected(self):
        with self.assertRaises(epoch.EpochError):
            epoch.summarize(["本人"])


class EpochPValueTest(unittest.TestCase):
    def test_twelve_of_twenty_matches_previous_implementation(self):
        # 20件中12件正答、見破られ率0.6。
        verdicts = make_verdicts(genuine_correct=6, genuine_wrong=4, fake_correct=6, fake_wrong=4)
        result = epoch.summarize(verdicts)
        self.assertEqual(result["deception_rate"], 0.6)
        self.assertAlmostEqual(result["p_value"], 0.5034, places=4)

    def test_eleven_of_twenty_matches_previous_implementation(self):
        # 20件中11件正答、見破られ率0.55。
        verdicts = make_verdicts(genuine_correct=6, genuine_wrong=4, fake_correct=5, fake_wrong=5)
        result = epoch.summarize(verdicts)
        self.assertEqual(result["deception_rate"], 0.55)
        self.assertAlmostEqual(result["p_value"], 0.8238, places=4)

    def test_exact_half_gives_p_value_of_one(self):
        verdicts = make_verdicts(genuine_correct=5, genuine_wrong=5, fake_correct=5, fake_wrong=5)
        self.assertEqual(epoch.summarize(verdicts)["p_value"], 1.0)

    def test_fifteen_of_twenty_is_significant(self):
        verdicts = make_verdicts(genuine_correct=8, genuine_wrong=2, fake_correct=7, fake_wrong=3)
        p_value = epoch.summarize(verdicts)["p_value"]
        self.assertAlmostEqual(p_value, 0.0414, places=4)
        self.assertLess(p_value, 0.05)

    def test_fourteen_of_twenty_is_not_significant(self):
        verdicts = make_verdicts(genuine_correct=7, genuine_wrong=3, fake_correct=7, fake_wrong=3)
        p_value = epoch.summarize(verdicts)["p_value"]
        self.assertAlmostEqual(p_value, 0.1153, places=4)
        self.assertGreater(p_value, 0.05)

    def test_all_correct_out_of_ten(self):
        verdicts = make_verdicts(genuine_correct=5, genuine_wrong=0, fake_correct=5, fake_wrong=0)
        self.assertEqual(epoch.summarize(verdicts)["p_value"], 0.001953125)

    def test_swapping_correct_and_incorrect_keeps_p_value(self):
        mostly_correct = make_verdicts(genuine_correct=8, genuine_wrong=2, fake_correct=7, fake_wrong=3)
        mostly_wrong = make_verdicts(genuine_correct=2, genuine_wrong=8, fake_correct=3, fake_wrong=7)
        self.assertEqual(
            epoch.summarize(mostly_correct)["p_value"],
            epoch.summarize(mostly_wrong)["p_value"],
        )


class EpochBalanceCheckTest(unittest.TestCase):
    def test_all_answers_are_fake_is_rejected(self):
        # Discriminator が中身を見ずに全部「生成文」と答えた退化ケース。
        verdicts = make_verdicts(genuine_correct=0, genuine_wrong=12, fake_correct=12, fake_wrong=0)
        with self.assertRaises(epoch.EpochError) as ctx:
            epoch.summarize(verdicts)
        self.assertIn("0.000", str(ctx.exception))

    def test_all_answers_are_genuine_is_rejected(self):
        # Discriminator が中身を見ずに全部「本人」と答えた退化ケース。
        verdicts = make_verdicts(genuine_correct=12, genuine_wrong=0, fake_correct=0, fake_wrong=12)
        with self.assertRaises(epoch.EpochError) as ctx:
            epoch.summarize(verdicts)
        self.assertIn("1.000", str(ctx.exception))

    def test_genuine_answer_rate_of_exactly_point_three_is_accepted(self):
        # 20サンプルのうち「本人」と答えた数がちょうど6件（0.3）。
        verdicts = make_verdicts(genuine_correct=6, genuine_wrong=4, fake_correct=10, fake_wrong=0)
        result = epoch.summarize(verdicts)
        self.assertEqual(result["genuine_answer_rate"], 0.3)

    def test_genuine_answer_rate_of_exactly_point_seven_is_accepted(self):
        # 20サンプルのうち「本人」と答えた数がちょうど14件（0.7）。
        verdicts = make_verdicts(genuine_correct=10, genuine_wrong=0, fake_correct=6, fake_wrong=4)
        result = epoch.summarize(verdicts)
        self.assertEqual(result["genuine_answer_rate"], 0.7)

    def test_genuine_answer_rate_of_point_two_five_is_rejected(self):
        # 20サンプルのうち「本人」と答えた数が5件（0.25）。
        verdicts = make_verdicts(genuine_correct=5, genuine_wrong=5, fake_correct=10, fake_wrong=0)
        with self.assertRaises(epoch.EpochError):
            epoch.summarize(verdicts)


class EpochCliTest(unittest.TestCase):
    def test_main_prints_json_with_all_fields(self):
        verdicts = make_verdicts(genuine_correct=9, genuine_wrong=3, fake_correct=8, fake_wrong=4)
        stdin_backup = sys.stdin
        sys.stdin = io.StringIO(json.dumps(verdicts))
        try:
            code, out, _err = run_main(epoch.main, ["-"])
        finally:
            sys.stdin = stdin_backup

        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(
            set(payload),
            {"total", "confusion", "deception_rate", "p_value", "genuine_answer_rate"},
        )

    def test_main_returns_nonzero_on_skewed_verdicts(self):
        verdicts = make_verdicts(genuine_correct=0, genuine_wrong=12, fake_correct=12, fake_wrong=0)
        stdin_backup = sys.stdin
        sys.stdin = io.StringIO(json.dumps(verdicts))
        try:
            code, _out, err = run_main(epoch.main, ["-"])
        finally:
            sys.stdin = stdin_backup

        self.assertNotEqual(code, 0)
        self.assertIn("倒れています", err)

    def test_subprocess_exit_code_is_zero_for_balanced_input(self):
        verdicts = make_verdicts(genuine_correct=9, genuine_wrong=3, fake_correct=8, fake_wrong=4)
        script = Path(__file__).resolve().parent / "epoch.py"
        proc = run_subprocess(script, [], stdin=json.dumps(verdicts))
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["total"], 24)

    def test_subprocess_exit_code_is_nonzero_for_skewed_input(self):
        verdicts = make_verdicts(genuine_correct=0, genuine_wrong=12, fake_correct=12, fake_wrong=0)
        script = Path(__file__).resolve().parent / "epoch.py"
        proc = run_subprocess(script, [], stdin=json.dumps(verdicts))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("倒れています", proc.stderr)


class PipelineFlowTest(unittest.TestCase):
    """60件規模の実例で、分割から集計までの数値の流れが破綻なく通ることを確かめる。"""

    def test_validation_and_test_batches_are_built_without_reusing_text(self):
        records = make_records(60)
        result = split.split_records(records, seed=SEED)
        validation_ids = result["assignments"]["validation"]
        test_ids = result["assignments"]["test"]
        self.assertEqual(len(validation_ids), 12)
        self.assertEqual(len(test_ids), 6)
        self.assertTrue(set(validation_ids).isdisjoint(test_ids))

        validation_batch = build_batch(validation_ids)
        test_batch = build_batch(test_ids)
        self.assertEqual(len(validation_batch), 24)
        self.assertEqual(len(test_batch), 12)

        for batch, ids in ((validation_batch, validation_ids), (test_batch, test_ids)):
            for source_id in ids:
                uses = [s for s in batch if s["source_id"] == source_id]
                self.assertEqual(len(uses), 2)
                self.assertEqual({s["role"] for s in uses}, {"本人", "生成文"})

    def test_epoch_summary_contains_every_field_report_needs(self):
        verdicts = make_verdicts(genuine_correct=6, genuine_wrong=4, fake_correct=6, fake_wrong=4)
        result = epoch.summarize(verdicts)
        self.assertEqual(
            set(result),
            {"total", "confusion", "deception_rate", "p_value", "genuine_answer_rate"},
        )

    def test_deception_rate_of_point_six_is_not_yet_convergence(self):
        # 20件中12件正答で見破られ率0.6。閾値は「未満」で収束のため、ちょうど0.6は収束しない。
        verdicts = make_verdicts(genuine_correct=6, genuine_wrong=4, fake_correct=6, fake_wrong=4)
        deception_rate = epoch.summarize(verdicts)["deception_rate"]
        self.assertEqual(deception_rate, 0.6)
        self.assertFalse(deception_rate < DECEPTION_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
