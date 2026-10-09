# GUI の色。起動したときの Windows の設定(アプリのモード)に合わせてライトかダークを選び、ttk の見た目を整える。
from __future__ import annotations

import ctypes
import os
import sys
import tkinter as tk
from tkinter import ttk

LIGHT = {
    "bg": "#f4f6f9", "panel": "#ffffff", "panel2": "#eef1f5", "line": "#d9dee6",
    "fg": "#1f2633", "muted": "#6b7584", "accent": "#2f6fd0", "accent_fg": "#ffffff",
    "select": "#dce8fb", "select_fg": "#10223f", "stripe": "#f8f9fb", "warn_bg": "#fff3b0", "warn_fg": "#5a4500",
    "error": "#b3261e",
}
DARK = {
    "bg": "#1b1e24", "panel": "#22262e", "panel2": "#2a2f38", "line": "#363c47",
    "fg": "#e3e7ee", "muted": "#9099a8", "accent": "#5b9cf0", "accent_fg": "#0c1626",
    "select": "#2d4466", "select_fg": "#f2f6fc", "stripe": "#262a32", "warn_bg": "#4a3f12", "warn_fg": "#f6e7a6",
    "error": "#ff8a80",
}
# 状態の色(model.STATES の順)。ライト/ダーク
STATE_COLORS = {
    "実装完了": ("#23a565", "#4cc38a"),
    "一部未実装": ("#d4891a", "#f0b13e"),
    "着手済": ("#2f7ed8", "#5aa2f0"),
    "未着手": ("#7d8896", "#8e98a6"),
    "撤退": ("#b0485a", "#e07a8c"),
    "証拠なし": ("#c9ced6", "#4a505b"),
}


def windows_is_dark() -> bool:
    """「アプリのモード」がダークなら True。読めなければライト。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def palette(dark: bool) -> dict:
    p = dict(DARK if dark else LIGHT)
    p["dark"] = dark
    p["states"] = {s: c[1 if dark else 0] for s, c in STATE_COLORS.items()}
    return p


def dark_titlebar(root: tk.Tk) -> None:
    """窓の枠(タイトルバー)もダークにする。Windows 10 20H1 以降。効かなければ何もしない。"""
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
    except Exception:
        pass


def asset(name: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name)


def set_icon(root: tk.Tk) -> None:
    try:
        if sys.platform == "win32":
            root.iconbitmap(default=asset("icon.ico"))
        else:
            root.iconphoto(True, tk.PhotoImage(file=asset("icon.png")))
    except Exception:
        pass


def dot(root: tk.Misc, color: str, size: int, bg: str | None = None, gap: int = 0) -> tk.PhotoImage:
    """塗った丸の小さな画像(状態の印)。縁は bg と色を混ぜてなめらかにする。右に gap だけ透明の余白。"""
    img = tk.PhotoImage(master=root, width=size + gap, height=size)
    c = _rgb(color)
    b = _rgb(bg) if bg else None
    r = size / 2
    for y in range(size):
        row = []
        for x in range(size):
            dist = ((x + 0.5 - r) ** 2 + (y + 0.5 - r) ** 2) ** 0.5
            a = max(0.0, min(1.0, r - 0.5 - dist + 0.5))
            if a <= 0:
                row.append(None)
            elif a >= 1 or b is None:
                row.append(color)
            else:
                row.append("#%02x%02x%02x" % tuple(round(cc * a + bb * (1 - a)) for cc, bb in zip(c, b)))
        for x, col in enumerate(row):
            if col:
                img.put(col, (x, y))
    return img


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def apply(root: tk.Tk, p: dict, font: tuple, bold: tuple, scale: float) -> None:
    px = lambda v: max(1, int(v * scale))  # noqa: E731
    st = ttk.Style(root)
    st.theme_use("clam")
    root.configure(background=p["bg"])
    st.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["panel"], bordercolor=p["line"],
                 lightcolor=p["panel"], darkcolor=p["line"], troughcolor=p["panel2"], focuscolor=p["accent"],
                 selectbackground=p["select"], selectforeground=p["select_fg"], insertcolor=p["fg"], font=font)
    st.configure("TFrame", background=p["bg"])
    st.configure("Panel.TFrame", background=p["panel"])
    st.configure("TLabel", background=p["bg"], foreground=p["fg"])
    st.configure("Panel.TLabel", background=p["panel"])
    st.configure("Muted.TLabel", foreground=p["muted"])
    st.configure("PanelMuted.TLabel", background=p["panel"], foreground=p["muted"])
    st.configure("Section.TLabel", background=p["panel"], foreground=p["muted"], font=bold)
    st.configure("Title.TLabel", font=(font[0], font[1] + 4, "bold"))
    st.configure("Name.TLabel", background=p["panel"], font=(font[0], font[1] + 5, "bold"))
    st.configure("Error.TLabel", foreground=p["error"])
    st.configure("TButton", background=p["panel2"], foreground=p["fg"], bordercolor=p["line"],
                 lightcolor=p["panel2"], darkcolor=p["panel2"], padding=(px(10), px(4)))
    st.map("TButton", background=[("disabled", p["bg"]), ("pressed", p["line"]), ("active", p["select"])],
           foreground=[("disabled", p["muted"])])
    st.configure("Accent.TButton", background=p["accent"], foreground=p["accent_fg"], bordercolor=p["accent"],
                 lightcolor=p["accent"], darkcolor=p["accent"], font=bold)
    st.map("Accent.TButton", background=[("disabled", p["panel2"]), ("pressed", p["accent"]), ("active", p["accent"])],
           foreground=[("disabled", p["muted"])])
    st.configure("TCheckbutton", background=p["bg"], foreground=p["fg"], indicatorbackground=p["panel"],
                 indicatorforeground=p["accent"], upperbordercolor=p["line"], lowerbordercolor=p["line"])
    st.map("TCheckbutton", background=[("active", p["bg"])], indicatorbackground=[("selected", p["panel"])])
    # 状態の札(押すと絞り込み)
    st.configure("Chip.TCheckbutton", background=p["panel"], foreground=p["fg"], padding=(px(10), px(4)),
                 bordercolor=p["line"], relief="flat", font=font)
    st.layout("Chip.TCheckbutton", [("Checkbutton.border", {"sticky": "nswe", "children": [
        ("Checkbutton.padding", {"sticky": "nswe", "children": [("Checkbutton.label", {"sticky": "nswe"})]})]})])
    st.map("Chip.TCheckbutton", background=[("selected", p["select"]), ("active", p["panel2"])],
           foreground=[("selected", p["select_fg"]), ("disabled", p["muted"])])
    # 表示の切り替え(表・カード・概要)は札と同じ見た目のラジオボタン
    st.configure("Chip.TRadiobutton", background=p["panel"], foreground=p["fg"], padding=(px(10), px(3)),
                 bordercolor=p["line"], relief="flat", font=font)
    st.layout("Chip.TRadiobutton", [("Radiobutton.border", {"sticky": "nswe", "children": [
        ("Radiobutton.padding", {"sticky": "nswe", "children": [("Radiobutton.label", {"sticky": "nswe"})]})]})])
    st.map("Chip.TRadiobutton", background=[("selected", p["accent"]), ("active", p["panel2"])],
           foreground=[("selected", p["accent_fg"])])
    st.configure("TMenubutton", background=p["panel2"], foreground=p["fg"], bordercolor=p["line"],
                 lightcolor=p["panel2"], darkcolor=p["panel2"], arrowcolor=p["fg"], padding=(px(10), px(4)))
    st.map("TMenubutton", background=[("active", p["select"])])
    st.configure("TEntry", fieldbackground=p["panel"], foreground=p["fg"], bordercolor=p["line"],
                 lightcolor=p["panel"], darkcolor=p["panel"], padding=px(3))
    st.map("TEntry", fieldbackground=[("disabled", p["bg"])], bordercolor=[("focus", p["accent"])],
           lightcolor=[("focus", p["accent"])])
    st.configure("TCombobox", fieldbackground=p["panel"], foreground=p["fg"], background=p["panel2"],
                 bordercolor=p["line"], arrowcolor=p["fg"], lightcolor=p["panel"], darkcolor=p["panel"], padding=px(3))
    st.map("TCombobox", fieldbackground=[("readonly", p["panel"]), ("disabled", p["bg"])],
           foreground=[("disabled", p["muted"])], selectbackground=[("readonly", p["panel"])],
           selectforeground=[("readonly", p["fg"])], arrowcolor=[("disabled", p["muted"])])
    root.option_add("*TCombobox*Listbox.background", p["panel"])
    root.option_add("*TCombobox*Listbox.foreground", p["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["select"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["select_fg"])
    root.option_add("*TCombobox*Listbox.font", font)
    for orient in ("Vertical", "Horizontal"):
        st.configure(f"{orient}.TScrollbar", background=p["panel2"], troughcolor=p["panel"], bordercolor=p["panel"],
                     lightcolor=p["panel2"], darkcolor=p["panel2"], arrowcolor=p["muted"], gripcount=0)
        st.map(f"{orient}.TScrollbar", background=[("active", p["line"])])
    st.configure("Treeview", background=p["panel"], fieldbackground=p["panel"], foreground=p["fg"],
                 bordercolor=p["line"], lightcolor=p["panel"], darkcolor=p["panel"], font=font,
                 rowheight=int(root.tk.call("font", "metrics", font, "-linespace")) + px(10))
    st.map("Treeview", background=[("selected", p["select"])], foreground=[("selected", p["select_fg"])])
    st.configure("Treeview.Heading", background=p["panel2"], foreground=p["muted"], bordercolor=p["line"],
                 lightcolor=p["panel2"], darkcolor=p["panel2"], relief="flat", font=bold, padding=(px(6), px(5)))
    st.map("Treeview.Heading", background=[("active", p["line"])])
    st.configure("Side.Treeview", background=p["bg"], fieldbackground=p["bg"], bordercolor=p["bg"],
                 lightcolor=p["bg"], darkcolor=p["bg"])
    # 詳細の下半分のタブ(文書・実装フォルダ・証拠・履歴)
    st.configure("Detail.TNotebook", background=p["panel"], bordercolor=p["line"], lightcolor=p["panel"],
                 darkcolor=p["panel"], tabmargins=(0, px(2), 0, 0))
    st.configure("Detail.TNotebook.Tab", background=p["panel2"], foreground=p["muted"], bordercolor=p["line"],
                 lightcolor=p["panel2"], darkcolor=p["panel2"], padding=(px(10), px(3)), font=font)
    st.map("Detail.TNotebook.Tab", background=[("selected", p["panel"])], foreground=[("selected", p["fg"])],
           lightcolor=[("selected", p["panel"])])
    st.configure("TPanedwindow", background=p["bg"])
    st.configure("Sash", sashthickness=px(6), background=p["bg"], lightcolor=p["bg"], bordercolor=p["bg"])


def style_listbox(lb: tk.Listbox, p: dict) -> None:
    lb.configure(background=p["panel"], foreground=p["fg"], selectbackground=p["select"],
                 selectforeground=p["select_fg"], relief="flat", borderwidth=0, highlightthickness=1,
                 highlightbackground=p["line"], highlightcolor=p["accent"], disabledforeground=p["muted"])
