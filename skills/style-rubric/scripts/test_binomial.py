"""binomial.py のテスト。python3 -m unittest discover -s skills/style-rubric/scripts で実行する。"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import binomial  # noqa: E402
from test_helpers import run_main, run_subprocess  # noqa: E402


class BinomialTestFunctionTest(unittest.TestCase):
    def test_exact_half_gives_p_value_of_one(self):
        _rate, p_value = binomial.binomial_test(20, 10)
        self.assertEqual(p_value, 1.0)

    def test_fifteen_of_twenty_is_significant(self):
        _rate, p_value = binomial.binomial_test(20, 15)
        self.assertAlmostEqual(p_value, 0.0414, places=4)
        self.assertLess(p_value, 0.05)

    def test_fourteen_of_twenty_is_not_significant(self):
        _rate, p_value = binomial.binomial_test(20, 14)
        self.assertAlmostEqual(p_value, 0.1153, places=4)
        self.assertGreater(p_value, 0.05)

    def test_all_correct_out_of_ten(self):
        _rate, p_value = binomial.binomial_test(10, 10)
        self.assertEqual(p_value, 0.001953125)

    def test_swapping_correct_and_incorrect_keeps_p_value(self):
        _rate, p_value = binomial.binomial_test(20, 15)
        _rate2, p_value2 = binomial.binomial_test(20, 5)
        self.assertEqual(p_value, p_value2)

    def test_rate_is_correct_over_total(self):
        rate, _p_value = binomial.binomial_test(20, 15)
        self.assertEqual(rate, 0.75)

    def test_correct_exceeding_total_is_rejected(self):
        with self.assertRaises(binomial.BinomialTestError):
            binomial.binomial_test(10, 11)

    def test_negative_correct_is_rejected(self):
        with self.assertRaises(binomial.BinomialTestError):
            binomial.binomial_test(10, -1)

    def test_non_positive_total_is_rejected(self):
        with self.assertRaises(binomial.BinomialTestError):
            binomial.binomial_test(0, 0)


class BinomialCliTest(unittest.TestCase):
    def test_main_prints_single_line_json_with_all_fields(self):
        code, out, _err = run_main(binomial.main, ["--total", "20", "--correct", "15"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 20)
        self.assertEqual(payload["correct"], 15)
        self.assertEqual(payload["rate"], 0.75)
        self.assertAlmostEqual(payload["p_value"], 0.0414, places=4)

    def test_main_returns_nonzero_when_correct_exceeds_total(self):
        code, _out, err = run_main(binomial.main, ["--total", "10", "--correct", "11"])
        self.assertNotEqual(code, 0)
        self.assertTrue(err)

    def test_main_returns_nonzero_when_total_is_not_positive(self):
        code, _out, err = run_main(binomial.main, ["--total", "0", "--correct", "0"])
        self.assertNotEqual(code, 0)
        self.assertTrue(err)

    def test_subprocess_exit_code_is_zero_for_good_input(self):
        script = Path(__file__).resolve().parent / "binomial.py"
        proc = run_subprocess(script, ["--total", "10", "--correct", "10"])
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["p_value"], 0.001953125)

    def test_subprocess_exit_code_is_nonzero_for_bad_input(self):
        script = Path(__file__).resolve().parent / "binomial.py"
        proc = run_subprocess(script, ["--total", "-1", "--correct", "0"])
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
