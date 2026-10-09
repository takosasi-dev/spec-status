# カード表示: 一覧を Canvas のタイル(アイコン・名前・状態の帯・Phase の棒・小さな印)で縦スクロールに並べる。
# 列の数は窓の幅で決める。クリックで選ぶ・Ctrl で足す・ダブルクリックで開く・右クリックでメニュー。
# 配置と印の計算は純関数(grid_layout・columns_for・truncate・badges)に分けて、窓なしで確かめる。
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable

from .model import ProjectStatus

TILE_W, TILE_H, GAP = 200, 92, 10       # 96dpi 基準
ICON = 40
REDRAW_DELAY_MS = 60                    # 窓の大きさを変えている間は描き直しをまとめる
EMPTY = "表示する物がありません"
ELLIPSIS = "…"
BADGE_VULN = "脆弱 {n}"
BADGE_STALE = "止 {days}日"
BADGE_CHANGED = "変"
BADGE_AC = "AC {done}/{total}"


# ---------- 純関数 ----------
def columns_for(width: int, tile_w: int, gap: int) -> int:
    """幅に入るタイルの列の数(最低1)。"""
    return max(1, (width - gap) // (tile_w + gap))


def grid_layout(n: int, width: int, tile_w: int, tile_h: int, gap: int) -> list[tuple[int, int, int]]:
    """n 枚のタイルの (左上 x, 左上 y, 幅)。列に入れた後の余りの幅はタイルを広げて埋める。"""
    cols = columns_for(width, tile_w, gap)
    w = max(tile_w, (width - gap * (cols + 1)) // cols)
    return [(gap + (i % cols) * (w + gap), gap + (i // cols) * (tile_h + gap), w) for i in range(n)]


def truncate(text: str, max_px: int, measure: Callable[[str], int]) -> str:
    """max_px に収まるよう末尾を … にする。"""
    if measure(text) <= max_px:
        return text
    lo, hi = 0, len(text)           # 収まる最長の先頭の長さを二分探索
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid] + ELLIPSIS) <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ELLIPSIS


def badges(ps: ProjectStatus) -> list[tuple[str, str]]:
    """タイルの小さな印 (種類, 文字)。種類: waiting / vuln / stale / changed / ac。"""
    out = []
    if ps.waiting != "なし":
        out.append(("waiting", ps.waiting))
    if ps.vulns and ps.vulns.get("count"):
        out.append(("vuln", BADGE_VULN.format(n=ps.vulns["count"])))
    if ps.stale_days:
        out.append(("stale", BADGE_STALE.format(days=ps.stale_days)))
    if ps.spec_changed:
        out.append(("changed", BADGE_CHANGED))
    if ps.ac:
        out.append(("ac", BADGE_AC.format(done=ps.ac[0], total=ps.ac[1])))
    return out


def phase_ratio(ps: ProjectStatus) -> float | None:
    """Phase の進み(0〜1)。done と last の両方が分かるときだけ。"""
    d, last = ps.done_phase, ps.last_phase
    if d is None or not last:
        return None
    return max(0.0, min(1.0, d / last))


# ---------- 部品で共通に使う物 ----------
def round_rect(c: tk.Canvas, x0, y0, x1, y1, r, **kw) -> int:
    """角の丸い四角(smooth の多角形)。"""
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


def bind_wheel(view: tk.Misc, canvas: tk.Canvas) -> None:
    """マウスがこの部品の上にあるときだけホイールで canvas を縦に動かす。"""
    def on_wheel(e):
        try:
            w = view.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):         # ポップアップの上など
            return
        if w is None or not (str(w) == str(view) or str(w).startswith(str(view) + ".")):
            return
        steps = max(1, abs(e.delta) // 120)
        canvas.yview_scroll(-steps if e.delta > 0 else steps, "units")
    view.bind_all("<MouseWheel>", on_wheel, add="+")


class CardView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        p, px = app.p, app.px
        self.canvas = tk.Canvas(self, background=p["bg"], highlightthickness=0, borderwidth=0,
                                yscrollincrement=px(40))
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        fam, size = app.font[0], app.font[1]
        self.small = (fam, max(1, size - 1))
        self.f_bold = tkfont.Font(root=app.root, font=app.bold)
        self.f_small = tkfont.Font(root=app.root, font=self.small)
        self.rows: list[ProjectStatus] = []
        self.selected: set[str] = set()
        self.imgs: list[tk.PhotoImage] = []
        self._width = 0
        self._job = None
        c = self.canvas
        c.bind("<Configure>", self._on_configure)
        c.bind("<Button-1>", self._on_click)
        c.bind("<Control-Button-1>", self._on_ctrl_click)
        c.bind("<Double-Button-1>", self._on_double)
        c.bind("<Button-3>", self._on_right)
        bind_wheel(self, c)

    # ---------- 外から ----------
    def refresh(self, rows: list[ProjectStatus], selected: set[str]) -> None:
        same = len(rows) == len(self.rows) and all(a is b for a, b in zip(rows, self.rows))
        self.selected = set(selected)
        if same and self._width:
            self._paint_selection()     # 中身が同じなら選択の色だけ塗り直す
            return
        self.rows = list(rows)
        self._redraw()

    # ---------- 描く ----------
    def _on_configure(self, e) -> None:
        if e.width == self._width:
            return
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(REDRAW_DELAY_MS, self._redraw)

    def _redraw(self) -> None:
        self._job = None
        c, p, px = self.canvas, self.app.p, self.app.px
        c.delete("all")
        self.imgs = []
        self._width = width = max(c.winfo_width(), 1)
        if not self.rows:
            c.create_text(width // 2, px(60), text=EMPTY, fill=p["muted"], font=self.app.font)
            c.configure(scrollregion=(0, 0, width, c.winfo_height()))
            return
        h, gap = px(TILE_H), px(GAP)
        pos = grid_layout(len(self.rows), width, px(TILE_W), h, gap)
        for i, ((x, y, w), ps) in enumerate(zip(pos, self.rows)):
            self._tile(i, ps, x, y, w, h)
        bottom = pos[-1][1] + h + gap
        c.configure(scrollregion=(0, 0, width, max(bottom, c.winfo_height())))
        self._paint_selection()

    def _tile(self, i: int, ps: ProjectStatus, x: int, y: int, w: int, h: int) -> None:
        c, p, px = self.canvas, self.app.p, self.app.px
        tag = (f"tile{i}",)
        color = p["states"].get(ps.state, p["muted"])
        round_rect(c, x, y, x + w, y + h, px(8), tags=(*tag, f"bg{i}", "bg"), width=1)
        c.create_rectangle(x + px(1), y + px(6), x + px(5), y + h - px(6), fill=color, width=0, tags=tag)
        # アイコン(無ければ頭文字の丸い四角)
        isz = px(ICON)
        ix, iy = x + px(14), y + px(12)
        img = self.app.icon(ps.project.key, isz)
        if img is not None:
            self.imgs.append(img)
            c.create_image(ix, iy, image=img, anchor="nw", tags=tag)
        else:
            round_rect(c, ix, iy, ix + isz, iy + isz, px(8), fill=p["panel2"], width=0, tags=tag)
            c.create_text(ix + isz // 2, iy + isz // 2, text=(ps.project.name[:1] or "?").upper(),
                          fill=p["muted"], font=(self.app.bold[0], self.app.bold[1] + 4, "bold"), tags=tag)
        tx, right = ix + isz + px(10), x + w - px(10)
        c.create_text(tx, iy, text=truncate(ps.project.name, right - tx, self.f_bold.measure), anchor="nw",
                      fill=p["fg"], font=self.app.bold, tags=tag)
        # 状態の丸と文字(+ Phase)
        sy = iy + px(26)
        r = px(4)
        c.create_oval(tx, sy - r, tx + 2 * r, sy + r, fill=color, width=0, tags=tag)
        phase = f"  {ps.done_phase}/{ps.last_phase if ps.last_phase is not None else '?'}" \
            if ps.done_phase is not None else ""
        c.create_text(tx + 2 * r + px(5), sy, text=ps.state + phase, anchor="w", fill=p["muted"],
                      font=self.small, tags=tag)
        # Phase の進みの棒
        ratio = phase_ratio(ps)
        if ratio is not None:
            by = iy + px(38)
            c.create_rectangle(tx, by, right, by + px(4), fill=p["panel2"], width=0, tags=tag)
            if ratio > 0:
                c.create_rectangle(tx, by, tx + (right - tx) * ratio, by + px(4), fill=color, width=0, tags=tag)
        # 小さな印(入る分だけ)
        colors = {"waiting": p["accent"], "vuln": p["states"]["撤退"], "stale": p["states"]["一部未実装"],
                  "changed": p["states"]["着手済"], "ac": p["muted"]}
        bx, by2 = x + px(14), y + h - px(22)
        for kind, text in badges(ps):
            tw = self.f_small.measure(text) + px(10)
            if bx + tw > x + w - px(8):
                break
            round_rect(c, bx, by2, bx + tw, by2 + px(16), px(6), fill=p["panel2"], width=0, tags=tag)
            c.create_text(bx + tw // 2, by2 + px(8), text=text, fill=colors[kind], font=self.small, tags=tag)
            bx += tw + px(4)

    def _paint_selection(self) -> None:
        c, p = self.canvas, self.app.p
        for i, ps in enumerate(self.rows):
            on = ps.project.key in self.selected
            c.itemconfigure(f"bg{i}", fill=p["select"] if on else p["panel"],
                            outline=p["accent"] if on else p["line"], width=2 if on else 1)

    # ---------- 操作 ----------
    def _hit(self) -> ProjectStatus | None:
        for t in self.canvas.gettags("current"):
            if t.startswith("tile"):
                i = int(t[4:])
                return self.rows[i] if i < len(self.rows) else None
        return None

    def _on_click(self, e) -> None:
        ps = self._hit()
        if ps:
            self.app.select_keys([ps.project.key])

    def _on_ctrl_click(self, e) -> None:
        ps = self._hit()
        if not ps:
            return
        keys = set(self.app.selected_keys()) ^ {ps.project.key}
        self.app.select_keys([r.project.key for r in self.rows if r.project.key in keys])

    def _on_double(self, e) -> None:
        ps = self._hit()
        if ps:
            self.app.open_ps(ps)

    def _on_right(self, e) -> None:
        ps = self._hit()
        if not ps:
            return
        sel = self.app.selected_keys()
        if ps.project.key in sel:       # 選んでいる物の上なら、選んでいる物全部に
            self.app.context_menu(e, [r for r in self.rows if r.project.key in sel])
        else:
            self.app.select_keys([ps.project.key])
            self.app.context_menu(e, [ps])
