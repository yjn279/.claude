"""スクリプトのテストで共通して使う補助関数。"""
import contextlib
import io
import subprocess
import sys


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
