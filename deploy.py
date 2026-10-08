# 開発フォルダの実行物を <vault>\spec-status\ にコピーし、VERSION.txt を書く(FR-33)。
# data\ の下は、無いときに config\ と events\ を作るほかは何も書かず何も消さない(INV-9)。
import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from datetime import datetime  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("specstatus.py", "start_gui.cmd", "README.md", "config.example.toml")
PACKAGE = "specstatus"


def _version() -> str:
    try:
        h = subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        h = "unknown"
    return f"{h} {datetime.now().astimezone().isoformat(timespec='seconds')}\n"


def deploy(vault: str) -> int:
    vault = os.path.abspath(vault)
    if not (os.path.isdir(os.path.join(vault, "説明書")) and os.path.isdir(os.path.join(vault, "開発ログ"))):
        print(f"vault ではありません(説明書\\ と 開発ログ\\ がありません): {vault}", file=sys.stderr)
        return 2
    dest = os.path.join(vault, "spec-status")
    os.makedirs(dest, exist_ok=True)
    for f in FILES:
        shutil.copy2(os.path.join(HERE, f), os.path.join(dest, f))
    shutil.copytree(os.path.join(HERE, PACKAGE), os.path.join(dest, PACKAGE), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    with open(os.path.join(dest, "VERSION.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_version())
    data = os.path.join(dest, "data")
    if not os.path.isdir(data):
        os.makedirs(os.path.join(data, "config"))
        os.makedirs(os.path.join(data, "events"))
    print(f"配置しました: {dest}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="SpecStatus を vault の spec-status\\ に配置する")
    ap.add_argument("--vault", required=True)
    sys.exit(deploy(ap.parse_args().vault))
