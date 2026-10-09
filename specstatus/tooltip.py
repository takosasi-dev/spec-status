# 表の行にマウスを止めたときの小窓(名前の全文・状態・待ち・メモ全文・脆弱性など)。
# tooltip_text は tkinter を使わない純関数。TreeTooltip は部品に結び付けて、止まって 500ms で出し、動いたら消す。
from __future__ import annotations

import tkinter as tk

from . import render
from . import strings as S
from .guilogic import extra_details, vulns_text
from .model import ProjectStatus

DELAY_MS = 500
L_STATE = "状態"
L_WAITING = "待ち"
L_PHASE = "Phase"
L_AC = "受け入れ基準"
L_NOTE = "メモ"
L_CHANGED = "仕様書の更新"
L_VULNS = "依存の脆弱性"
L_WORST = "(一番重い: {worst})"
L_STALE = "止まっている"
STALE_VALUE = "{days} 日(最後に動いた日 {date})"
L_RELEASE = "GitHub の版"


def tooltip_text(ps: ProjectStatus) -> str:
    """小窓の中身。1行目は名前の全文、その下に「見出し: 値」。値の無い行は出さない。"""
    lines = [ps.project.name, f"{L_STATE}: {ps.state}"]

    def add(label: str, value) -> None:
        if value:
            lines.append(f"{label}: {value}")

    add(L_WAITING, ps.waiting if ps.waiting != "なし" else "")
    add(L_PHASE, render.phase_text(ps) if ps.done_phase is not None else "")
    add(L_AC, render.ac_text(ps))
    add(L_NOTE, ps.folded.note)
    add(L_CHANGED, ps.spec_changed)
    if ps.vulns and ps.vulns.get("count"):
        worst = ps.vulns.get("worst")
        add(L_VULNS, vulns_text(ps) + (L_WORST.format(worst=worst) if worst else ""))
    if ps.stale_days:
        add(L_STALE, STALE_VALUE.format(days=ps.stale_days, date=ps.last_activity or "-"))
    add(L_RELEASE, (ps.github or {}).get("release"))
    extra = extra_details(ps)               # v0.7.0 の欄(記録漏れ・未確定・見込みなど)。詳細の欄と同じ文字
    for key, label in S.EXTRA_FIELDS:
        add(label, extra.get(key))
    return "\n".join(lines)


class TreeTooltip:
    """widget(主に ttk.Treeview)の上でマウスが同じ行に DELAY_MS 止まったら小窓を出す。
    text_for_event(event) が None か空を返したら出さない。行が変わる・離れる・押すと消す。"""

    def __init__(self, widget: tk.Misc, text_for_event, app) -> None:
        self.widget, self.text_for_event, self.app = widget, text_for_event, app
        self.row = None            # 今見ている行(identify_row。無い部品は None)
        self.after_id = None
        self.tip: tk.Toplevel | None = None
        widget.bind("<Motion>", self._motion, add="+")
        widget.bind("<Leave>", self._hide_event, add="+")
        widget.bind("<ButtonPress>", self._hide_event, add="+")

    def _row_of(self, event):
        ident = getattr(self.widget, "identify_row", None)
        return ident(event.y) if ident else None

    def _motion(self, event) -> None:
        row = self._row_of(event)
        if self.tip is not None and row == self.row:
            return                                   # 出ている行の中で動いただけ
        self.hide()
        self.row = row
        self.after_id = self.widget.after(DELAY_MS, lambda: self._show(event))

    def _hide_event(self, _event=None) -> None:
        self.hide()
        self.row = None

    def _cancel(self) -> None:
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def hide(self) -> None:
        self._cancel()
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None

    def _show(self, event) -> None:
        self.after_id = None
        text = self.text_for_event(event)
        if not text:
            return
        app, p, px = self.app, self.app.p, self.app.px
        tip = self.tip = tk.Toplevel(self.widget)
        tip.withdraw()
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.configure(bg=p["line"])                  # 1px の枠の色
        tk.Label(tip, text=text, justify="left", anchor="w", bg=p["panel"], fg=p["fg"], font=app.font,
                 wraplength=px(420), padx=px(8), pady=px(6)).pack(padx=1, pady=1)
        tip.update_idletasks()
        w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
        sw, sh = tip.winfo_screenwidth(), tip.winfo_screenheight()
        x, y = event.x_root + px(14), event.y_root + px(18)
        if x + w > sw:
            x = max(0, sw - w)
        if y + h > sh:
            y = max(0, event.y_root - h - px(6))     # 下に入らなければポインタの上に
        tip.geometry(f"+{x}+{y}")
        tip.deiconify()
