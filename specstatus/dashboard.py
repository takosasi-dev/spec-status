# 概要の画面: 状態のドーナツ・分類ごとの完了率・推移の折れ線・今週動いた物・今日のおすすめを、縦スクロールのカードに並べる。
# 幅が広ければ2列、狭ければ1列。項目を押すと app.select_keys で表の選択に渡す。
# 数の計算は純関数(donut_segments・category_rates・this_week・chart_xy)に分けて、窓なしで確かめる。
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime
from tkinter import ttk

from . import history
from .cards import bind_wheel, truncate
from .guilogic import category_tree, count_by_state
from .model import STATES, ProjectStatus

T_STATES = "状態の内訳"
T_RATES = "分類ごとの完了率"
T_TREND = "進み具合の推移({weeks}週)"
T_WEEK = "今週動いた物"
T_RECOMMEND = "今日のおすすめ"
NONE_YET = "まだありません"
TOTAL_UNIT = "件"
LEGEND_ROW = "{state}  {n}"
LEGEND_DONE = "実装完了"
LEGEND_DOING = "途中(着手済・一部未実装)"
RATE_TEXT = "{done}/{total}  {pct}%"
WEEK_SUB = "{state} ・ {at}"
RATE_LIMIT = 10
WEEK_LIMIT = 10
RECOMMEND_LIMIT = 5
WEEKS_DEFAULT = 12
WIDE_PX = 820           # 96dpi 基準。これより広ければ2列


# ---------- 純関数 ----------
def donut_segments(counts: dict[str, int]) -> list[tuple[str, float, float]]:
    """ドーナツの (状態, 始まりの角度, 広がり)。12時から時計回り(Tk の角度なので広がりは負)。0件の状態は出さない。"""
    total = sum(counts.get(s, 0) for s in STATES)
    out, start = [], 90.0
    if not total:
        return out
    for s in STATES:
        n = counts.get(s, 0)
        if n:
            ext = -360.0 * n / total
            out.append((s, start, ext))
            start += ext
    return out


def category_rates(statuses: list[ProjectStatus], limit: int = RATE_LIMIT) -> list[tuple[str, int, int]]:
    """分類(1段目と2段目)ごとの (パス, 実装完了, 全部)。件数の多い順に limit 件(同数は分類の木の順)。"""
    rows = [(path, done, n) for path, _parent, _name, n, done in category_tree(statuses)]
    return sorted(rows, key=lambda r: -r[2])[:limit]


def _at(ps: ProjectStatus) -> datetime | None:
    r = ps.folded.last_record
    return datetime.fromisoformat(r.at) if r else None


def this_week(statuses: list[ProjectStatus], today: date, limit: int = WEEK_LIMIT) -> list[ProjectStatus]:
    """最後の記録が今週(月〜日)の物。新しい順に limit 件。"""
    mon, sun = history.week_range(today)
    hits = [ps for ps in statuses
            if ps.folded.last_record and mon <= date.fromisoformat(ps.folded.last_record.at[:10]) <= sun]
    hits.sort(key=lambda ps: _at(ps).timestamp(), reverse=True)
    return hits[:limit]


def chart_xy(values: list[int], x0: float, y0: float, x1: float, y1: float, hi: int) -> list[float]:
    """折れ線の座標 [x, y, x, y, ...]。(x0, y0) が左上、(x1, y1) が右下、y1 が 0、y0 が hi。"""
    n = len(values)
    out: list[float] = []
    for i, v in enumerate(values):
        out += [x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0.5), y1 - (y1 - y0) * (v / hi if hi else 0)]
    return out


def _recommend(statuses: list[ProjectStatus], today: date) -> list[tuple[ProjectStatus, int, list[str]]]:
    try:
        from . import recommend      # 担当 A と並行で作っているので、無ければ空
        return list(recommend.recommend(statuses, today, RECOMMEND_LIMIT))
    except Exception:
        return []


# ---------- 部品 ----------
class DashboardView(ttk.Frame):
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
        self.inner = ttk.Frame(self.canvas)
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        bind_wheel(self, self.canvas)
        self.small = (app.font[0], max(1, app.font[1] - 1))
        self.f_font = tkfont.Font(root=app.root, font=app.font)
        self.cols = 0
        self.imgs: list[tk.PhotoImage] = []
        self.series: list[tuple[str, int, int]] = []
        self.rates: list[tuple[str, int, int]] = []

        self.c_states, b = self._card(T_STATES)
        self.donut = self._canvas(b, px(180))
        self.c_rates, b = self._card(T_RATES)
        self.rate_cv = self._canvas(b, px(40))
        self.rate_cv.bind("<Configure>", lambda e: self._draw_rates())
        self.c_trend, b = self._card(T_TREND.format(weeks=WEEKS_DEFAULT))
        self.trend_title = self.c_trend.title
        self.trend = self._canvas(b, px(230))
        self.trend.bind("<Configure>", lambda e: self._draw_trend())
        self.c_week, self.week_body = self._card(T_WEEK)
        self.c_rec, self.rec_body = self._card(T_RECOMMEND)

    def _card(self, title: str) -> tuple[ttk.Frame, ttk.Frame]:
        px = self.app.px
        card = ttk.Frame(self.inner, style="Panel.TFrame", padding=(px(14), px(10)))
        card.title = ttk.Label(card, text=title, style="Section.TLabel")
        card.title.pack(anchor="w", pady=(0, px(6)))
        body = ttk.Frame(card, style="Panel.TFrame")
        body.pack(fill="both", expand=True)
        return card, body

    def _canvas(self, parent, height: int) -> tk.Canvas:
        c = tk.Canvas(parent, height=height, background=self.app.p["panel"], highlightthickness=0, borderwidth=0)
        c.pack(fill="x")
        return c

    def _on_resize(self, e) -> None:
        self.canvas.itemconfigure(self.win, width=e.width)
        cols = 2 if e.width >= self.app.px(WIDE_PX) else 1
        if cols != self.cols:
            self.cols = cols
            self._place_cards()

    def _place_cards(self) -> None:
        px = self.app.px
        for card in (self.c_states, self.c_rates, self.c_trend, self.c_week, self.c_rec):
            card.grid_forget()
        if self.cols == 2:
            places = [(self.c_states, 0, 0, 1), (self.c_rates, 0, 1, 1), (self.c_trend, 1, 0, 2),
                      (self.c_week, 2, 0, 1), (self.c_rec, 2, 1, 1)]
        else:
            places = [(c, i, 0, 1) for i, c in enumerate((self.c_states, self.c_trend, self.c_rates,
                                                           self.c_week, self.c_rec))]
        for col in (0, 1):
            self.inner.columnconfigure(col, weight=1 if col < self.cols else 0, uniform="dash" if col < self.cols else "")
        for card, row, col, span in places:
            card.grid(row=row, column=col, columnspan=span, sticky="nsew", padx=px(6), pady=px(6))

    # ---------- 外から ----------
    def refresh(self, statuses: list[ProjectStatus]) -> None:
        today = date.today()
        board = self.app.board
        weeks = (board.config.get("board", {}).get("progress_weeks", WEEKS_DEFAULT) if board else WEEKS_DEFAULT)
        self.series = history.series(statuses, today, weeks)
        self.trend_title.configure(text=T_TREND.format(weeks=weeks))
        self.rates = category_rates(statuses)
        self.rate_cv.configure(height=max(1, len(self.rates)) * self.app.px(26))
        self.imgs = []
        self._draw_donut(count_by_state(statuses))
        self._draw_rates()
        self._draw_trend()
        self._fill_list(self.week_body, [(ps, WEEK_SUB.format(state=ps.state, at=ps.folded.last_record.at[:16]
                                                               .replace("T", " "))) for ps in this_week(statuses, today)])
        self._fill_list(self.rec_body, [(ps, " ・ ".join(reasons)) for ps, _score, reasons in _recommend(statuses, today)])

    # ---------- 描く ----------
    def _draw_donut(self, counts: dict[str, int]) -> None:
        c, p, px = self.donut, self.app.p, self.app.px
        c.delete("all")
        size, thick = px(170), px(24)
        x0, y0 = px(6), px(5)
        box = (x0 + thick / 2, y0 + thick / 2, x0 + size - thick / 2, y0 + size - thick / 2)
        segs = donut_segments(counts)
        if not segs:
            c.create_oval(*box, outline=p["panel2"], width=thick)
        for s, start, ext in segs:
            if ext <= -359.9:       # Tk は 360 度の弧を描かない
                c.create_oval(*box, outline=p["states"][s], width=thick)
            else:
                c.create_arc(*box, start=start, extent=ext, style="arc", outline=p["states"][s], width=thick)
        cx, cy = x0 + size / 2, y0 + size / 2
        total = sum(counts.values())
        c.create_text(cx, cy - px(6), text=str(total), fill=p["fg"],
                      font=(self.app.bold[0], self.app.bold[1] + 10, "bold"))
        c.create_text(cx, cy + px(18), text=TOTAL_UNIT, fill=p["muted"], font=self.small)
        lx, ly, r = x0 + size + px(24), y0 + px(14), px(5)
        for i, s in enumerate(STATES):
            y = ly + i * px(25)
            n = counts.get(s, 0)
            c.create_oval(lx, y - r, lx + 2 * r, y + r, fill=p["states"][s], width=0)
            c.create_text(lx + 2 * r + px(8), y, text=LEGEND_ROW.format(state=s, n=n), anchor="w",
                          fill=p["fg"] if n else p["muted"], font=self.app.font)
            if total:
                c.create_text(lx + px(150), y, text=f"{round(100 * n / total)}%", anchor="e", fill=p["muted"],
                              font=self.small)

    def _draw_rates(self) -> None:
        c, p, px = self.rate_cv, self.app.p, self.app.px
        c.delete("all")
        w = c.winfo_width()
        if w <= 1:
            return
        if not self.rates:
            c.create_text(0, px(12), text=NONE_YET, anchor="w", fill=p["muted"], font=self.app.font)
            return
        label_w, right_w, row_h = min(px(170), w // 3), px(96), px(26)
        bx0, bx1 = label_w + px(8), w - right_w
        color = p["states"]["実装完了"]
        for i, (path, done, total) in enumerate(self.rates):
            y = i * row_h + row_h // 2
            c.create_text(0, y, text=truncate(path, label_w, self.f_font.measure), anchor="w", fill=p["fg"],
                          font=self.app.font)
            if bx1 > bx0:
                c.create_rectangle(bx0, y - px(5), bx1, y + px(5), fill=p["panel2"], width=0)
                if done:
                    c.create_rectangle(bx0, y - px(5), bx0 + (bx1 - bx0) * done / total, y + px(5),
                                       fill=color, width=0)
            c.create_text(w, y, text=RATE_TEXT.format(done=done, total=total, pct=round(100 * done / total)),
                          anchor="e", fill=p["muted"], font=self.small)

    def _draw_trend(self) -> None:
        c, p, px = self.trend, self.app.p, self.app.px
        c.delete("all")
        w, h = c.winfo_width(), int(c.cget("height"))
        pts = self.series
        if w <= 1 or not pts:
            return
        x0, y0, x1, y1 = px(36), px(28), w - px(14), h - px(26)
        hi = max(1, max(max(d, g) for _, d, g in pts))
        # 目盛り(0・半分・最大)
        for v in sorted({0, hi // 2, hi}):
            y = y1 - (y1 - y0) * v / hi
            c.create_line(x0, y, x1, y, fill=p["line"])
            c.create_text(x0 - px(6), y, text=str(v), anchor="e", fill=p["muted"], font=self.small)
        # 日付(MM-DD)。狭ければ間引く
        n = len(pts)
        step = 1
        while step < n and (x1 - x0) / max(1, (n - 1)) * step < px(46):
            step += 1
        for i in range(n - 1, -1, -step):       # 最後(今日)は必ず出す
            x = x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0.5)
            c.create_text(x, y1 + px(6), text=pts[i][0][5:], anchor="n", fill=p["muted"], font=self.small)
        r = px(3)
        for idx, key in ((2, "着手済"), (1, "実装完了")):
            color = p["states"][key]
            xy = chart_xy([pt[idx] for pt in pts], x0, y0, x1, y1, hi)
            if n > 1:
                c.create_line(*xy, fill=color, width=max(1, px(2)))
            for j in range(0, len(xy), 2):
                c.create_oval(xy[j] - r, xy[j + 1] - r, xy[j] + r, xy[j + 1] + r, fill=color, width=0)
        # 凡例(右上)
        lx = x1
        for key, label in (("着手済", LEGEND_DOING), ("実装完了", LEGEND_DONE)):
            t = c.create_text(lx, px(10), text=label, anchor="e", fill=p["fg"], font=self.small)
            bx = c.bbox(t)[0]
            c.create_rectangle(bx - px(16), px(8), bx - px(4), px(12), fill=p["states"][key], width=0)
            lx = bx - px(28)

    def _fill_list(self, body: ttk.Frame, items: list[tuple[ProjectStatus, str]]) -> None:
        px = self.app.px
        for w in body.winfo_children():
            w.destroy()
        if not items:
            ttk.Label(body, text=NONE_YET, style="PanelMuted.TLabel").pack(anchor="w")
            return
        for ps, sub in items:
            row = ttk.Frame(body, style="Panel.TFrame", cursor="hand2")
            row.pack(fill="x", pady=(0, px(6)))
            img = self.app.icon(ps.project.key, px(18))
            parts = []
            if img is not None:
                self.imgs.append(img)
                parts.append(ttk.Label(row, image=img, style="Panel.TLabel", cursor="hand2"))
                parts[-1].grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, px(8)), pady=(px(2), 0))
            name = ttk.Label(row, text=ps.project.name, style="Panel.TLabel", font=self.app.bold, cursor="hand2")
            name.grid(row=0, column=1, sticky="w")
            info = ttk.Label(row, text=sub, style="PanelMuted.TLabel", cursor="hand2")
            info.grid(row=1, column=1, sticky="w")
            row.columnconfigure(1, weight=1)
            key = ps.project.key
            for w in (row, name, info, *parts):
                w.bind("<Button-1>", lambda e, k=key: self.app.select_keys([k]))
