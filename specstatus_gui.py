# exe(窓アプリ)の入口。GUI だけを開く。CLI は specstatus.py を python で使う。
# vault は --vault、無ければ exe の隣の vault.txt(build.py が書く)。どちらも無ければ理由を窓で出す。
import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import os  # noqa: E402

VAULT_FILE = "vault.txt"


def _here() -> str:
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault")
    ap.add_argument("--config")
    a, _ = ap.parse_known_args()
    vault = a.vault
    if not vault:
        try:
            with open(os.path.join(_here(), VAULT_FILE), encoding="utf-8-sig") as f:
                vault = f.read().strip()
        except OSError:
            pass
    if not vault or not os.path.isdir(vault):
        from tkinter import Tk, messagebox
        Tk().withdraw()
        messagebox.showerror("SpecStatus", f"vault の場所が分かりません。\n{os.path.join(_here(), VAULT_FILE)} に vault のパスを1行で書くか、--vault を付けて起動してください。")
        return 2
    from specstatus import gui
    return gui.run(vault, a.config)


if __name__ == "__main__":
    sys.exit(main())
