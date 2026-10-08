# SpecStatus の CLI の入口。__pycache__ を作らないようにし、標準出力を UTF-8 にしてから cli.main を呼ぶ。
# vault は --vault、無ければこのファイルが置かれたフォルダの1つ上(§2)。
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402


def _utf8_console() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


if __name__ == "__main__":
    _utf8_console()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from specstatus.cli import main  # noqa: E402
    sys.exit(main(default_vault=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
