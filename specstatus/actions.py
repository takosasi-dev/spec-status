# 表やカードの右クリックのメニューと、キー操作(1〜5 で状態・W で待ち・/ で検索・Enter で開く・F2 でメモ・? で一覧)。
# 実際の記録・コピー・開く処理は本体の app に任せる(使うのは INTERFACES.md 6章 担当 D に書いた物だけ)。
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from . import strings as S
from .guilogic import copy_text
from .model import RECORDABLE_STATES, WAITINGS, ProjectStatus

M_OPEN = "Obsidian で開く"
M_IMPL = "実装フォルダを開く"
M_GITHUB = "GitHub を開く"
M_STATE = "状態を変える"
M_WAITING = "待ちを変える"
M_COPY = "Claude Code に渡す文をコピー"
M_DIFF = "仕様書の差分を渡す文をコピー"
HELP_TITLE = "キー操作"
HELP_CLOSE = "Esc で閉じる"

KEY_HELP = [
    ("1〜5", "状態を変える(" + "・".join(f"{i}={s}" for i, s in enumerate(RECORDABLE_STATES, 1)) + ")"),
    ("W", "待ちを順に変える(なし → 確認待ち → 実物待ち)"),
    ("/", "検索欄へ"),
    ("Enter", "Obsidian で開く"),
    ("F2", "メモを書く"),
    ("?", "この一覧"),
    ("右クリック", "操作のメニュー"),
]

_TYPING = (tk.Entry, tk.Text, tk.Spinbox, ttk.Entry, ttk.Spinbox)   # ttk.Combobox は ttk.Entry の子
_MODIFIERS = 0x4 | 0x8 | 0x20000                                     # Ctrl・Alt(Windows の Alt は 0x20000)


def _menu(app, parent) -> tk.Menu:
    p = app.p
    return tk.Menu(parent, tearoff=0, bg=p["panel"], fg=p["fg"], activebackground=p["select"],
                   activeforeground=p["select_fg"], selectcolor=p["fg"], font=app.font, bd=0, relief="flat")


def _diff_prompt(ps: ProjectStatus) -> str | None:
    """担当 A の snapshots が無い・写しが無い・読めないときは None(メニューに出さない)。"""
    try:
        from . import snapshots
        return snapshots.diff_prompt(ps) if snapshots.diff(ps) is not None else None
    except Exception:            # 並行して作っている部品。どう壊れていてもメニューは出す
        return None


def build_menu(app, ps_list: list[ProjectStatus]) -> tk.Menu:
    """ps_list(1件以上)への操作のメニュー。開く系とコピーの差分は1件のときだけ。呼び手が tk_popup する。"""
    m = _menu(app, app.root)
    single = ps_list[0] if len(ps_list) == 1 else None
    if single:
        m.add_command(label=M_OPEN, command=app.open_primary)
        if any(i.exists_here for i in single.folded.impl):
            m.add_command(label=M_IMPL, command=lambda: app.open_impl_of(single))
        url = (single.github or {}).get("url")
        if url:
            m.add_command(label=M_GITHUB, command=lambda: webbrowser.open(url))
        m.add_separator()

    for label, values, current, setter in (
            (M_STATE, RECORDABLE_STATES, single.state if single else None, app.set_state),
            (M_WAITING, WAITINGS, single.waiting if single else None, app.set_waiting)):
        sub = _menu(app, m)
        var = tk.StringVar(m, value=current or "")
        setattr(sub, "_var", var)                    # 消えないように持たせる(印の表示に使う)
        for v in values:
            sub.add_radiobutton(label=v, value=v, variable=var, command=lambda v=v, f=setter: f(ps_list, v))
        m.add_cascade(label=label, menu=sub)
    m.add_separator()

    template = (app.board.config.get("gui", {}).get("copy_template") if app.board else None) or S.DEFAULT_COPY_TEMPLATE
    m.add_command(label=M_COPY, command=lambda: app.copy_text("\n\n".join(copy_text(template, ps) for ps in ps_list)))
    if single:
        prompt = _diff_prompt(single)
        if prompt:
            m.add_command(label=M_DIFF, command=lambda: app.copy_text(prompt))
    return m


def _typing(app) -> bool:
    try:
        w = app.root.focus_get()
    except (KeyError, tk.TclError):              # ttk.Combobox の一覧などで起きる
        return True
    return isinstance(w, _TYPING)


def next_waiting(current: str) -> str:
    return WAITINGS[(WAITINGS.index(current) + 1) % len(WAITINGS)] if current in WAITINGS else WAITINGS[0]


def on_key(app, event):
    """キー1つ分。扱ったら "break"。文字を打てる欄にフォーカスがあるとき・Ctrl/Alt 付きのときは何もしない。"""
    if event.state & _MODIFIERS or _typing(app):
        return None
    k = event.keysym
    if k in ("1", "2", "3", "4", "5"):
        sel = app.selected()
        if sel:
            app.set_state(sel, RECORDABLE_STATES[int(k) - 1])
    elif k in ("w", "W"):
        sel = app.selected()
        if sel:
            app.set_waiting(sel, next_waiting(sel[0].waiting))
    elif k == "slash":
        app.focus_search()
    elif k in ("Return", "KP_Enter"):
        w = app.root.focus_get()
        if w is not None and w.bind("<Return>"):
            return None                              # 部品が自分で Enter を扱う(表の <Return> など)。二重に開かない
        app.open_primary()
    elif k == "F2":
        app.focus_note()
    elif k == "question":
        show_help(app)
    else:
        return None
    return "break"


def bind_keys(app) -> None:
    """app.root にキーを結ぶ(root の子の部品で押されたキーは全部ここを通る)。"""
    app.root.bind("<Key>", lambda e: on_key(app, e), add="+")


def show_help(app) -> tk.Toplevel:
    """キーの一覧の小窓。Esc か ? で閉じる。"""
    p, px = app.p, app.px
    win = tk.Toplevel(app.root, bg=p["bg"], padx=px(16), pady=px(12))
    win.title(HELP_TITLE)
    win.transient(app.root)
    win.resizable(False, False)
    for r, (key, desc) in enumerate(KEY_HELP):
        tk.Label(win, text=key, bg=p["bg"], fg=p["accent"], font=app.bold, anchor="w").grid(
            row=r, column=0, sticky="w", padx=(0, px(14)), pady=px(2))
        tk.Label(win, text=desc, bg=p["bg"], fg=p["fg"], font=app.font, anchor="w").grid(row=r, column=1, sticky="w")
    tk.Label(win, text=HELP_CLOSE, bg=p["bg"], fg=p["muted"], font=app.font).grid(
        row=len(KEY_HELP), column=0, columnspan=2, sticky="w", pady=(px(8), 0))
    win.bind("<Escape>", lambda e: win.destroy())
    win.bind("<question>", lambda e: win.destroy())
    win.focus_set()
    return win
