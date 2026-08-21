"""split.py のテスト。python3 -m unittest discover -s skills/style-rubric/scripts で実行する。"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import split  # noqa: E402


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


def make_records(n, *, topic_of=None, date_of=None, length_of=None):
    """テスト用の文章一覧を組み立てる。id は r0, r1, ... と振る。"""
    records = []
    for i in range(n):
        length = length_of(i) if length_of else 40
        record = {"id": f"r{i}", "text": "あ" * length}
        if topic_of:
            record["topic"] = topic_of(i)
        if date_of:
            record["date"] = date_of(i)
        records.append(record)
    return records


def write_temp_json(records):
    """records を一時 JSON ファイルへ書き、そのパスを返す。"""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(records, f)
    f.close()
    return f.name


class SplitRecordsTest(unittest.TestCase):
    def test_covers_every_input_without_overlap(self):
        records = make_records(60)
        result = split.split_records(records, seed=1)

        all_assigned = [rid for ids in result["assignments"].values() for rid in ids]
        self.assertEqual(len(all_assigned), len(set(all_assigned)))
        self.assertEqual(set(all_assigned), {r["id"] for r in records})

    def test_exact_counts_for_60_records(self):
        records = make_records(60)
        result = split.split_records(records, seed=1)

        self.assertEqual(
            result["counts"],
            {"train": 42, "validation": 12, "test": 6},
        )

    def test_same_seed_is_reproducible(self):
        records = make_records(60, length_of=lambda i: 20 + i)
        first = split.split_records(records, seed=42)
        second = split.split_records(records, seed=42)
        self.assertEqual(first, second)

    def test_different_seed_can_differ(self):
        records = make_records(60, length_of=lambda i: 20 + i)
        first = split.split_records(records, seed=1)
        second = split.split_records(records, seed=2)
        self.assertNotEqual(first["assignments"], second["assignments"])

    def test_stratified_proportions_track_overall_distribution(self):
        # 話題・時期・長さのいずれも偏った入力を作る。
        # 前半は話題A・早い日付・短文、後半は話題B・遅い日付・長文にそろえ、
        # 三つの偏りが連動する厳しめのケースにする。
        def topic_of(i):
            return "A" if i < 40 else "B"

        def date_of(i):
            year = 2020 if i < 40 else 2024
            month = (i % 12) + 1
            return f"{year}-{month:02d}-01"

        def length_of(i):
            return 20 if i < 40 else 200

        records = make_records(60, topic_of=topic_of, date_of=date_of, length_of=length_of)
        result = split.split_records(records, seed=7)

        id_to_topic = {r["id"]: r["topic"] for r in records}
        overall_a_ratio = sum(1 for r in records if r["topic"] == "A") / len(records)

        for set_name in split.SET_NAMES:
            ids = result["assignments"][set_name]
            a_ratio = sum(1 for rid in ids if id_to_topic[rid] == "A") / len(ids)
            self.assertLess(
                abs(a_ratio - overall_a_ratio), 0.15,
                f"{set_name} の話題Aの比率 {a_ratio:.3f} が全体の {overall_a_ratio:.3f} から乖離しすぎている",
            )

        # 層の要約にも、時期・長さ・話題の3種の層が現れている。
        periods = {s["key"]["period"] for s in result["strata"]}
        lengths = {s["key"]["length"] for s in result["strata"]}
        topics = {s["key"]["topic"] for s in result["strata"]}
        self.assertTrue(periods.issuperset({"period0", "period1", "period2"}))
        self.assertTrue(lengths.issuperset({"length0", "length1", "length2"}))
        self.assertEqual(topics, {"A", "B"})

    def test_fewer_than_30_records_is_rejected(self):
        records = make_records(29)
        with self.assertRaises(split.SplitError) as ctx:
            split.split_records(records, seed=1)
        self.assertIn("30件", str(ctx.exception))

    def test_partial_topic_labels_are_rejected(self):
        records = make_records(30, topic_of=lambda i: "A" if i < 10 else None)
        for r in records:
            if r.get("topic") is None:
                r.pop("topic", None)
        with self.assertRaises(split.SplitError):
            split.split_records(records, seed=1)

    def test_non_dict_record_is_rejected(self):
        records = make_records(29) + ["idtext"]
        with self.assertRaises(split.SplitError):
            split.split_records(records, seed=1)

    def test_non_string_date_is_rejected(self):
        records = make_records(30)
        records[0]["date"] = 20230101
        with self.assertRaises(split.SplitError):
            split.split_records(records, seed=1)

    def test_output_includes_seed_and_breakdowns(self):
        records = make_records(60)
        result = split.split_records(records, seed=99)

        self.assertEqual(result["seed"], 99)
        self.assertEqual(set(result["counts"]), set(split.SET_NAMES))
        self.assertTrue(result["strata"])
        for stratum in result["strata"]:
            self.assertEqual(set(stratum["counts"]), set(split.SET_NAMES))
            self.assertEqual(sum(stratum["counts"].values()), stratum["size"])


class SplitCliTest(unittest.TestCase):
    def test_main_returns_nonzero_below_minimum(self):
        path = write_temp_json(make_records(10))
        code, _out, err = run_main(split.main, ["--seed", "1", path])
        self.assertNotEqual(code, 0)
        self.assertIn("30件", err)

    def test_main_returns_nonzero_on_partial_topic(self):
        records = make_records(30, topic_of=lambda i: "A" if i < 5 else None)
        for r in records:
            if r.get("topic") is None:
                r.pop("topic", None)
        path = write_temp_json(records)
        code, _out, err = run_main(split.main, ["--seed", "1", path])
        self.assertNotEqual(code, 0)
        self.assertIn("話題の札", err)

    def test_main_succeeds_and_prints_json(self):
        path = write_temp_json(make_records(60))
        code, out, _err = run_main(split.main, ["--seed", "1", path])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["counts"]["train"], 42)

    def test_subprocess_exit_code_is_nonzero_for_bad_input(self):
        # main() を直接呼ぶテストだけでなく、実際にプロセスとして起動した場合の
        # 終了コードも確認する。
        script = Path(__file__).resolve().parent / "split.py"
        proc = run_subprocess(script, ["--seed", "1"], stdin=json.dumps(make_records(5)))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("30件", proc.stderr)

    def test_subprocess_exit_code_is_zero_for_good_input(self):
        script = Path(__file__).resolve().parent / "split.py"
        proc = run_subprocess(script, ["--seed", "1"], stdin=json.dumps(make_records(60)))
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["counts"]["train"], 42)


if __name__ == "__main__":
    unittest.main()
