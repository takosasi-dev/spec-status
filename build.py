# メインPC用の exe(GUI の窓アプリ)を作る: PyInstaller(onedir・窓)→ dist\SpecStatus\ に vault.txt と VERSION.txt を書く。
# 使い方: python build.py --vault <vault> [--zip](--zip で Release に付ける zip も作る)
import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import zipfile  # noqa: E402

from deploy import _version  # noqa: E402
from specstatus.update import ASSET_SUFFIX  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "SpecStatus"


def main() -> int:
    ap = argparse.ArgumentParser(description="SpecStatus の exe を作る")
    ap.add_argument("--vault", required=True, help="exe が開く vault(dist の vault.txt に書く)")
    ap.add_argument("--zip", action="store_true", help="Release に付ける dist/SpecStatus-v<版>-windows.zip も作る(vault.txt は入れない)")
    args = ap.parse_args()
    vault = os.path.abspath(args.vault)
    if not (os.path.isdir(os.path.join(vault, "説明書")) and os.path.isdir(os.path.join(vault, "開発ログ"))):
        print(f"vault ではありません(説明書\\ と 開発ログ\\ がありません): {vault}", file=sys.stderr)
        return 2
    dist = os.path.join(HERE, "dist")
    # 証拠の読み手は core が importlib で名前から読むので、パッケージ丸ごと入れる
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--name", NAME,
                    "--paths", HERE, "--collect-submodules", "specstatus",
                    "--icon", os.path.join(HERE, "specstatus", "assets", "icon.ico"),
                    "--add-data", os.path.join(HERE, "specstatus", "assets") + os.pathsep + "specstatus/assets",
                    "--distpath", dist, "--workpath", os.path.join(HERE, "build", "pyi"),
                    "--specpath", os.path.join(HERE, "build"), os.path.join(HERE, "specstatus_gui.py")],
                   cwd=HERE, check=True)
    out = os.path.join(dist, NAME)
    for fn, text in (("vault.txt", vault + "\n"), ("VERSION.txt", _version())):
        with open(os.path.join(out, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(f"完成: {os.path.join(out, NAME + '.exe')}")
    if args.zip:
        print(f"Release 用: {make_zip(out)}")
    return 0


def make_zip(out: str) -> str:
    """dist/SpecStatus を SpecStatus/ の形で zip にする。この PC の vault の場所(vault.txt)と VERSION.txt は入れない。"""
    from specstatus import __version__
    path = os.path.join(os.path.dirname(out), f"{NAME}-v{__version__}{ASSET_SUFFIX}")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, _dirs, files in os.walk(out):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, out)
                if rel not in ("vault.txt", "VERSION.txt"):
                    z.write(full, f"{NAME}/{rel.replace(os.sep, '/')}")
    return path


if __name__ == "__main__":
    sys.exit(main())
