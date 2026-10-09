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
        vault = _ask_vault()            # Release の zip には vault.txt が無いので、初回に選んでもらう
        if not vault:
            return 2
    from specstatus import gui
    return gui.run(vault, a.config)


def _ask_vault() -> str | None:
    """vault を選ばせ、spec-status\\ がある物なら exe の隣の vault.txt に書いて返す。"""
    from tkinter import Tk, filedialog, messagebox
    root = Tk()
    root.withdraw()
    path = os.path.join(_here(), VAULT_FILE)
    while True:
        vault = filedialog.askdirectory(title="SpecStatus: Obsidian の vault のフォルダを選んでください", mustexist=True)
        if not vault:
            messagebox.showerror("SpecStatus", f"vault の場所が分かりません。\n{path} に vault のパスを1行で書くか、--vault を付けて起動してください。")
            root.destroy()
            return None
        vault = os.path.abspath(vault)
        if os.path.isdir(os.path.join(vault, "spec-status")):
            break
        messagebox.showerror("SpecStatus", f"このフォルダに spec-status\\ がありません。\n{vault}\n先に vault へ SpecStatus を置いてください(README の「入れ方」)。")
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(vault + "\n")
    except OSError:
        pass                            # 書けなくても今回は開く
    root.destroy()
    return vault


if __name__ == "__main__":
    sys.exit(main())
