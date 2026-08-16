"""epoch.py のテスト。python3 -m unittest discover -s skills/style-rubric/scripts で実行する。"""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import binomial  # noqa: E402
import epoch  # noqa: E402


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


def run_main(argv):
    """epoch.main を呼び、(戻り値, 標準出力, 標準エラー出力) を返す。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = epoch.main(argv)
    return code, out.getvalue(), err.getvalue()


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

    def test_rate_and_p_value_match_binomial_module_called_with_same_numbers(self):
        verdicts = make_verdicts(genuine_correct=9, genuine_wrong=3, fake_correct=8, fake_wrong=4)
        result = epoch.summarize(verdicts)

        correct = result["confusion"]["genuine"]["genuine"] + result["confusion"]["fake"]["fake"]
        expected_rate, expected_p_value = binomial.binomial_test(result["total"], correct)
        self.assertEqual(result["deception_rate"], expected_rate)
        self.assertEqual(result["p_value"], expected_p_value)

    def test_empty_input_is_rejected(self):
        with self.assertRaises(epoch.EpochError):
            epoch.summarize([])

    def test_unknown_label_is_rejected(self):
        with self.assertRaises(epoch.EpochError):
            epoch.summarize([{"truth": "本人", "verdict": "不明"}])


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
    def test_main_prints_single_line_json_with_all_fields(self):
        verdicts = make_verdicts(genuine_correct=9, genuine_wrong=3, fake_correct=8, fake_wrong=4)
        stdin_backup = sys.stdin
        sys.stdin = io.StringIO(json.dumps(verdicts))
        try:
            code, out, _err = run_main(["-"])
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
            code, _out, err = run_main(["-"])
        finally:
            sys.stdin = stdin_backup

        self.assertNotEqual(code, 0)
        self.assertIn("倒れています", err)

    def test_subprocess_exit_code_is_zero_for_balanced_input(self):
        verdicts = make_verdicts(genuine_correct=9, genuine_wrong=3, fake_correct=8, fake_wrong=4)
        script = Path(__file__).resolve().parent / "epoch.py"
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(verdicts),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["total"], 24)

    def test_subprocess_exit_code_is_nonzero_for_skewed_input(self):
        verdicts = make_verdicts(genuine_correct=0, genuine_wrong=12, fake_correct=12, fake_wrong=0)
        script = Path(__file__).resolve().parent / "epoch.py"
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(verdicts),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("倒れています", proc.stderr)


if __name__ == "__main__":
    unittest.main()
