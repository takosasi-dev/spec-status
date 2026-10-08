# SpecStatus の GUI(§9.9。tkinter)。一覧の表示・絞り込み・詳細・記録・取り消し・Obsidian/エクスプローラで開く。
# 記録は core.write_mark、出力は core.build でだけ書く(INV-11)。読み込みと書き込みは別スレッド、部品はメインスレッドだけで触る。
# 表の中身の計算は guilogic(純関数)に任せる。
from __future__ import annotations

import ctypes
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.parse
from collections import deque
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from . import core
from . import guilogic as G
from . import strings as S
from . import theme
from .model import RECORDABLE_STATES, STATES, WAITINGS, Board, ProjectStatus
from .textutil import resolve, slash

UNDO_MAX = 20           # §9.9 の固定値
SEARCH_DELAY_MS = 300   # §9.9 の固定値
POLL_MS = 50


def open_in_obsidian(parent: tk.Misc, abs_path: str) -> None:
    try:
        os.startfile("obsidian://open?path=" + urllib.parse.quote(abs_path))
    except Exception:
        messagebox.showinfo(S.OBSIDIAN_FAILED_TITLE, S.OBSIDIAN_FAILED.format(path=abs_path), parent=parent)


class App:
    def __init__(self, root: tk.Tk, vault: str, config_path: str | None):
        self.core = core
        self.root, self.vault, self.config_path = root, vault, config_path
        self.board: Board | None = None
        self.rows: dict[str, ProjectStatus] = {}        # 表の iid -> ProjectStatus
        self.sort: tuple[str, bool] | None = None        # (列, 降順)。None は一覧ノートと同じ並び
        self.undo_stack: deque[list[tuple[str, dict]]] = deque(maxlen=UNDO_MAX)
        self.busy = False
        self.build_warn = ""
        self.q: queue.Queue = queue.Queue()
        self._search_job = None
        self._build()
        self._poll()
        self.reload()

    # ---------- 部品 ----------
    def _build(self) -> None:
        r = self.root
        r.title(S.TITLE)
        theme.set_icon(r)
        self.scale = _dpi_scale(r)
        px = self.px = lambda v: int(v * self.scale)  # noqa: E731  96dpi 基準の大きさを画面の拡大率に合わせる
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        w, h = (px(1360), px(840)) if sw >= px(1360) and sh >= px(840) else (int(sw * 0.9), int(sh * 0.9))
        r.geometry(f"{w}x{h}")
        r.minsize(min(px(1000), sw), min(px(600), sh))
        family = S.FONT_FAMILY if S.FONT_FAMILY in tkfont.families(r) else tkfont.nametofont("TkDefaultFont").actual("family")
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            tkfont.nametofont(name).configure(family=family, size=S.FONT_SIZE)
        self.font, self.bold = (family, S.FONT_SIZE), (family, S.FONT_SIZE, "bold")
        self.p = p = theme.palette(theme.windows_is_dark())
        theme.apply(r, p, self.font, self.bold, self.scale)
        if p["dark"]:
            theme.dark_titlebar(r)
        dot = px(10)
        self.dots = {s: theme.dot(r, c, dot, p["panel"], gap=px(8)) for s, c in p["states"].items()}
        self.chip_dots = {s: theme.dot(r, c, dot, p["panel"], gap=px(2)) for s, c in p["states"].items()}
        r.columnconfigure(0, weight=1)
        r.rowconfigure(5, weight=1)

        # 1. 見出しの帯: アイコン・名前 / 読み込みの時刻・ボタン
        head = ttk.Frame(r, padding=(px(14), px(10), px(14), px(4)))
        head.grid(row=0, column=0, sticky="ew")
        try:
            big = tk.PhotoImage(master=r, file=theme.asset("icon.png"))
            self.logo = big.subsample(max(1, round(256 / px(32))))
            ttk.Label(head, image=self.logo).pack(side="left", padx=(0, px(8)))
        except tk.TclError:
            pass
        ttk.Label(head, text=S.APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(head, text=S.APP_SUB, style="Muted.TLabel").pack(side="left", padx=(px(10), 0), pady=(px(4), 0))
        self.reload_btn = ttk.Button(head, text=S.RELOAD, command=self.reload)
        self.reload_btn.pack(side="right")
        self.board_btn = ttk.Button(head, text=S.OPEN_BOARD, command=self.open_board)
        self.board_btn.pack(side="right", padx=px(6))
        self.gen_lbl = ttk.Label(head, text="", style="Muted.TLabel")
        self.gen_lbl.pack(side="right", padx=px(8))

        # 黄色の1行(読めなかった証拠)
        self.warn_lbl = tk.Label(r, text="", bg=p["warn_bg"], fg=p["warn_fg"], anchor="w", padx=px(14), pady=px(3),
                                 font=self.font)
        self.warn_lbl.grid(row=1, column=0, sticky="ew")
        self.warn_lbl.grid_remove()

        # 2. 進み具合の帯と状態の札(押すと絞り込み)
        summary = ttk.Frame(r, style="Panel.TFrame", padding=(px(14), px(10)))
        summary.grid(row=2, column=0, sticky="ew", padx=px(14), pady=(px(4), px(8)))
        summary.columnconfigure(0, weight=1)
        top = ttk.Frame(summary, style="Panel.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        self.scope_lbl = ttk.Label(top, text="", style="Panel.TLabel", font=self.bold)
        self.scope_lbl.pack(side="left")
        self.ratio_lbl = ttk.Label(top, text="", style="PanelMuted.TLabel")
        self.ratio_lbl.pack(side="left", padx=px(10))
        self.bar = tk.Canvas(summary, height=px(10), background=p["panel"], highlightthickness=0, borderwidth=0)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(px(6), px(8)))
        self.bar.bind("<Configure>", lambda e: self._draw_bar())
        self.bar_counts: dict[str, int] = {}
        chips = ttk.Frame(summary, style="Panel.TFrame")
        chips.grid(row=2, column=0, sticky="w")
        self.chip_vars = {s: tk.BooleanVar() for s in STATES}
        self.chips = {}
        for s in STATES:
            b = ttk.Checkbutton(chips, text=S.CHIP.format(state=s, count=0), variable=self.chip_vars[s],
                                style="Chip.TCheckbutton", image=self.chip_dots[s], compound="left",
                                command=self.refresh_table, takefocus=False)
            b.pack(side="left", padx=(0, px(4)))
            self.chips[s] = b

        # 3. 絞り込みの帯
        tools = ttk.Frame(r, padding=(px(14), 0, px(14), px(6)))
        tools.grid(row=3, column=0, sticky="ew")
        ttk.Label(tools, text=S.SEARCH).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._on_search())
        self.search = ttk.Entry(tools, textvariable=self.search_var, width=32)
        self.search.pack(side="left", padx=(px(6), px(14)))
        self.waiting_var, self.conflict_var = tk.BooleanVar(), tk.BooleanVar()
        ttk.Checkbutton(tools, text=S.WAITING_ONLY, variable=self.waiting_var,
                        command=self.refresh_table).pack(side="left", padx=px(4))
        ttk.Checkbutton(tools, text=S.CONFLICT_ONLY, variable=self.conflict_var,
                        command=self.refresh_table).pack(side="left", padx=px(4))
        self.count_lbl = ttk.Label(tools, text="", style="Muted.TLabel")
        self.count_lbl.pack(side="right")

        self.loading_lbl = ttk.Label(r, text=S.LOADING, padding=(px(14), 0), style="Muted.TLabel")
        self.loading_lbl.grid(row=4, column=0, sticky="w")
        self.loading_lbl.grid_remove()

        # 4. 左の分類・まん中の表・右の詳細
        pane = ttk.PanedWindow(r, orient="horizontal")
        pane.grid(row=5, column=0, sticky="nsew", padx=px(14))
        self._build_side(pane)
        left = ttk.Frame(pane)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        pane.add(left, weight=4)

        self.table = ttk.Frame(left)
        self.table.grid(row=0, column=0, sticky="nsew")
        self.table.columnconfigure(0, weight=1)
        self.table.rowconfigure(0, weight=1)
        cols = [k for k, _ in S.COLUMNS[1:]]     # 状態は #0 の列に丸と一緒に出す
        self.tree = ttk.Treeview(self.table, columns=cols, show="tree headings", selectmode="extended")
        widths = {"state": 112, "name": 200, "spec_dir": 200, "phase": 56, "waiting": 68,
                  "last": 120, "source": 130, "conflict": 72}
        for k, title in S.COLUMNS:
            cid = "#0" if k == "state" else k
            self.tree.heading(cid, text=title, anchor="w", command=lambda c=k: self.sort_by(c))
            self.tree.column(cid, width=px(widths[k]), minwidth=px(40), stretch=False,
                             anchor="center" if k in ("phase", "conflict") else "w")
        self.tree.configure(displaycolumns=[c for c in cols if c != "spec_dir"])   # 仕様書フォルダは左の分類と詳細で見る
        self.tree.tag_configure("stripe", background=p["stripe"])
        self.tree.tag_configure("none", foreground=p["muted"])
        self.tree.tag_configure("conflict", foreground=p["error"])
        ys = ttk.Scrollbar(self.table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Configure>", lambda e: self._fit_columns(e.width))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_select())
        self.tree.bind("<Return>", lambda e: self.open_primary())
        self.tree.bind("<Double-Button-1>", lambda e: self.open_primary() if self.tree.identify_region(e.x, e.y) in ("cell", "tree") else None)

        self.empty = ttk.Frame(self.table, padding=px(16), style="Panel.TFrame")
        ttk.Label(self.empty, text=S.EMPTY, style="Panel.TLabel").pack(pady=(0, px(8)))
        ttk.Button(self.empty, text=S.CLEAR_FILTERS, command=self.clear_filters).pack()

        self.error = ttk.Frame(left, padding=px(16))
        self.error_lbl = ttk.Label(self.error, text="", style="Error.TLabel", justify="left", wraplength=px(700))
        self.error_lbl.pack(anchor="nw")

        self._build_detail(pane)
        self._build_edit()
        self.pane = pane
        r.after(1, self._place_sashes)

        r.bind_all("<Control-f>", lambda e: (self.search.focus_set(), "break")[1])
        r.bind_all("<F5>", lambda e: self.reload())
        r.bind_all("<Control-z>", lambda e: (self.undo(), "break")[1])

    def _fit_columns(self, width: int) -> None:
        """プロジェクトの列で表の幅に合わせる(Treeview は狭くなっても列を縮めないため)。"""
        shown = ["#0", *self.tree.cget("displaycolumns")]
        fixed = sum(self.tree.column(c, "width") for c in shown if c != "name")
        self.tree.column("name", width=max(self.px(120), width - fixed - 2))

    def _place_sashes(self) -> None:
        """左の分類と右の詳細の幅を決める(PanedWindow は最初に中身の希望の幅で分けてしまうため)。"""
        self.root.update_idletasks()
        w = self.pane.winfo_width()
        if w > 1:
            self.pane.sashpos(0, self.px(230))
            self.pane.sashpos(1, max(self.px(600), w - self.px(420)))

    def _build_side(self, pane) -> None:
        px = self.px
        side = ttk.Frame(pane, padding=(0, 0, px(8), 0))
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        pane.add(side, weight=1)
        ttk.Label(side, text=S.CATEGORIES, style="Muted.TLabel", font=self.bold).grid(row=0, column=0, sticky="w",
                                                                                      pady=(0, px(4)))
        self.side = ttk.Treeview(side, columns=("n",), show="tree", selectmode="browse", style="Side.Treeview")
        self.side.column("#0", width=px(150), minwidth=px(80), stretch=True)
        self.side.column("n", width=px(44), minwidth=px(30), stretch=False, anchor="e")
        self.side.grid(row=1, column=0, sticky="nsew")
        self.side.bind("<<TreeviewSelect>>", lambda e: self._on_category())
        self.category: str | None = None

    def _listbox(self, parent, height: int, grow: bool = False) -> tk.Listbox:
        f = ttk.Frame(parent, style="Panel.TFrame")
        f.pack(fill="both" if grow else "x", expand=grow, pady=(0, self.px(10)))
        lb = tk.Listbox(f, height=height, activestyle="none", exportselection=False, font=self.font)
        theme.style_listbox(lb, self.p)
        sb = ttk.Scrollbar(f, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return lb

    def _build_detail(self, pane) -> None:
        px, p = self.px, self.p
        wrap = ttk.Frame(pane, padding=(px(10), 0, 0, 0))
        pane.add(wrap, weight=3)
        d = ttk.Frame(wrap, style="Panel.TFrame", padding=(px(16), px(14)))
        d.pack(fill="both", expand=True)
        self.d_name = ttk.Label(d, text=S.DETAIL_NONE, style="Name.TLabel", wraplength=px(380))
        self.d_name.pack(anchor="w")
        self.d_badge = tk.Label(d, text="", font=self.bold, padx=px(10), pady=px(2), borderwidth=0)
        self.d_badge.pack(anchor="w", pady=(px(6), px(8)))
        self.d_badge.pack_forget()
        self.d_grid = ttk.Frame(d, style="Panel.TFrame")
        self.d_grid.pack(fill="x", pady=(0, px(10)))
        self.d_grid.columnconfigure(1, weight=1)
        self.d_info: dict[str, ttk.Label] = {}
        for i, (k, label) in enumerate(S.DETAIL_FIELDS):
            ttk.Label(self.d_grid, text=label, style="PanelMuted.TLabel").grid(row=i, column=0, sticky="nw",
                                                                               padx=(0, px(12)), pady=px(1))
            v = ttk.Label(self.d_grid, text="", style="Panel.TLabel", wraplength=px(290), justify="left")
            v.grid(row=i, column=1, sticky="w", pady=px(1))
            self.d_info[k] = v
        ttk.Label(d, text=S.DOCS, style="Section.TLabel").pack(anchor="w", pady=(0, px(3)))
        self.d_docs = self._listbox(d, 2)
        self.d_docs.bind("<Double-Button-1>", lambda e: self.open_doc())
        ttk.Label(d, text=S.IMPLS, style="Section.TLabel").pack(anchor="w", pady=(0, px(3)))
        self.d_impl = self._listbox(d, 2)
        self.d_impl.master.pack_configure(pady=(0, px(4)))
        self.d_impl.bind("<<ListboxSelect>>", lambda e: self._update_impl_buttons())
        bar = ttk.Frame(d, style="Panel.TFrame")
        bar.pack(anchor="w", pady=(0, px(10)))
        self.impl_open = ttk.Button(bar, text=S.IMPL_OPEN, command=self.open_impl)
        self.impl_add = ttk.Button(bar, text=S.IMPL_ADD, command=self.add_impl)
        self.impl_rm = ttk.Button(bar, text=S.IMPL_REMOVE, command=self.remove_impl)
        for b in (self.impl_open, self.impl_add, self.impl_rm):
            b.pack(side="left", padx=(0, px(4)))
        ttk.Label(d, text=S.EVIDENCE, style="Section.TLabel").pack(anchor="w", pady=(0, px(3)))
        self.d_ev = self._listbox(d, 3)
        ttk.Label(d, text=S.HISTORY, style="Section.TLabel").pack(anchor="w", pady=(0, px(3)))
        self.d_hist = self._listbox(d, 2, grow=True)
        self.d_impl_paths: list = []

    def _build_edit(self) -> None:
        px = self.px
        e = ttk.Frame(self.root, style="Panel.TFrame", padding=(px(14), px(8)))
        e.grid(row=6, column=0, sticky="ew", pady=(px(10), 0))
        ttk.Label(e, style="Panel.TLabel", text=S.EDIT_STATE).pack(side="left")
        self.e_state = ttk.Combobox(e, state="readonly", width=10, values=[S.NO_CHANGE, *RECORDABLE_STATES])
        self.e_state.set(S.NO_CHANGE)
        self.e_state.pack(side="left", padx=(px(4), px(12)))
        ttk.Label(e, style="Panel.TLabel", text=S.EDIT_DONE).pack(side="left")
        self.e_done = ttk.Entry(e, width=4)
        self.e_done.pack(side="left", padx=(px(4), px(12)))
        ttk.Label(e, style="Panel.TLabel", text=S.EDIT_LAST).pack(side="left")
        self.e_last = ttk.Entry(e, width=4)
        self.e_last.pack(side="left", padx=(px(4), px(12)))
        ttk.Label(e, style="Panel.TLabel", text=S.EDIT_WAITING).pack(side="left")
        self.e_wait = ttk.Combobox(e, state="readonly", width=9, values=[S.NO_CHANGE, *WAITINGS])
        self.e_wait.set(S.NO_CHANGE)
        self.e_wait.pack(side="left", padx=(px(4), px(12)))
        ttk.Label(e, style="Panel.TLabel", text=S.EDIT_NOTE).pack(side="left")
        vcmd = (self.root.register(lambda p: len(p) <= 200), "%P")
        self.e_note = ttk.Entry(e, width=36, validate="key", validatecommand=vcmd)
        self.e_note.pack(side="left", padx=(4, 4), fill="x", expand=True)
        self.e_clear_note = ttk.Button(e, text=S.CLEAR_NOTE, command=self.clear_note)
        self.e_clear_note.pack(side="left", padx=(0, 10))
        self.e_record = ttk.Button(e, text=S.RECORD, command=self.record, style="Accent.TButton")
        self.e_record.pack(side="left", padx=2)
        self.e_undo = ttk.Button(e, text=S.UNDO, command=self.undo)
        self.e_undo.pack(side="left", padx=2)
        self.e_copy = ttk.Button(e, text=S.COPY, command=self.copy)
        self.e_copy.pack(side="left", padx=2)

    # ---------- スレッドとの受け渡し(部品はここ=メインスレッドでだけ触る) ----------
    def _poll(self) -> None:
        try:
            while True:
                fn, args = self.q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._poll)

    def _run(self, work, done) -> None:
        """work() を別スレッドで走らせ、戻り値を done(結果, 例外) にメインスレッドで渡す。"""
        self._set_busy(True)

        def target():
            try:
                res, err = work(), None
            except Exception as ex:     # 何が起きても窓を固めない
                res, err = None, ex
            self.q.put((done, (res, err)))
        threading.Thread(target=target, daemon=True).start()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if busy:
            self.loading_lbl.grid()
        else:
            self.loading_lbl.grid_remove()
        self.reload_btn.configure(state="disabled" if busy else "normal")
        self._update_edit()

    # ---------- 読み込み ----------
    def reload(self) -> None:
        if self.busy:
            return
        self._run(lambda: self.core.load(self.vault, self.config_path), self._loaded)

    def _loaded(self, board, err) -> None:
        self._set_busy(False)
        if err is not None:
            self._show_error(err)
            return
        self.build_warn = ""
        self._apply_board(board)

    def _show_error(self, err: Exception) -> None:
        self.board = None
        text = str(err)
        if getattr(err, "path", ""):
            text += "\n" + S.ERROR_PATH.format(path=err.path)
        self.error_lbl.configure(text=f"{S.ERROR_TITLE}\n\n{text}")
        self.table.grid_remove()
        self.error.grid(row=0, column=0, sticky="nsew")
        self.board_btn.configure(state="disabled")
        for b in self.chips.values():
            b.configure(state="disabled")
        self._show_detail()
        self._update_edit()

    def _apply_board(self, board: Board) -> None:
        keep = {self.rows[i].project.key for i in self.tree.selection() if i in self.rows}
        self.board = board
        self.error.grid_remove()
        self.table.grid()
        self.board_btn.configure(state="normal")
        self.gen_lbl.configure(text=S.GENERATED.format(at=datetime.now().strftime("%Y-%m-%d %H:%M"), pc=board.pc_name))
        for b in self.chips.values():
            b.configure(state="normal")
        self._refresh_side()
        items = [S.UNREADABLE_ITEM.format(reader=u.reader, reason=u.reason) for u in board.unreadable]
        if not items and self.build_warn:
            items = [self.build_warn]
        if items:
            self.warn_lbl.configure(text=S.UNREADABLE_LINE.format(items=" / ".join(items)))
            self.warn_lbl.grid()
        else:
            self.warn_lbl.grid_remove()
        self.refresh_table(keep)

    # ---------- 表 ----------
    def _on_search(self) -> None:
        if self._search_job:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(SEARCH_DELAY_MS, self.refresh_table)

    def refresh_table(self, keep: set[str] | None = None) -> None:
        self._search_job = None
        if self.board is None:
            return
        if keep is None:
            keep = {self.rows[i].project.key for i in self.tree.selection() if i in self.rows}
        self._refresh_summary()
        rows = G.filter_rows(self.board.statuses, {s for s, v in self.chip_vars.items() if v.get()}, self.category,
                             self.waiting_var.get(), self.conflict_var.get(), self.search_var.get())
        if self.sort:
            rows = G.sort_rows(rows, *self.sort)
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        sel = []
        for n, ps in enumerate(rows):
            iid = f"r{n}"
            self.rows[iid] = ps
            vals = G.row_values(ps)
            tags = ["stripe"] if n % 2 else []
            if ps.conflict:
                tags.append("conflict")
            elif ps.state == "証拠なし":
                tags.append("none")
            self.tree.insert("", "end", iid=iid, text=vals[0], image=self.dots.get(ps.state, ""), values=vals[1:],
                             tags=tags)
            if ps.project.key in keep:
                sel.append(iid)
        for k, title in S.COLUMNS:
            mark = (S.SORT_DESC if self.sort[1] else S.SORT_ASC) if self.sort and self.sort[0] == k else ""
            self.tree.heading("#0" if k == "state" else k, text=title + mark)
        self.count_lbl.configure(text=S.ROW_COUNT.format(n=len(rows), total=len(self.board.statuses)))
        if rows:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.3, anchor="center")
        self.tree.selection_set(sel)
        if sel:
            self.tree.see(sel[0])
        self.on_select()

    def sort_by(self, column: str) -> None:
        self.sort = (column, not self.sort[1]) if self.sort and self.sort[0] == column else (column, False)
        self.refresh_table()

    def clear_filters(self) -> None:
        for v in self.chip_vars.values():
            v.set(False)
        self.waiting_var.set(False)
        self.conflict_var.set(False)
        self.search_var.set("")
        self.category = None
        if self.side.exists("__all__"):
            self.side.selection_set("__all__")
        self.refresh_table()

    # ---------- 分類と進み具合 ----------
    def _refresh_side(self) -> None:
        keep = self.category
        self.side.delete(*self.side.get_children())
        sts = self.board.statuses
        self.side.insert("", "end", iid="__all__", text=S.CAT_ALL, values=(len(sts),), open=True)
        for path, parent, name, n, _done in G.category_tree(sts):
            self.side.insert(parent or "", "end", iid=path, text=name, values=(n,))
        target = keep if keep and self.side.exists(keep) else "__all__"
        self.category = None if target == "__all__" else target
        self.side.selection_set(target)
        self.side.see(target)

    def _on_category(self) -> None:
        sel = self.side.selection()
        cat = None if not sel or sel[0] == "__all__" else sel[0]
        if cat != self.category:
            self.category = cat
            self.refresh_table()

    def _refresh_summary(self) -> None:
        scope = [ps for ps in self.board.statuses if G.in_category(ps, self.category)]
        counts = G.count_by_state(scope)
        for s, b in self.chips.items():
            b.configure(text=S.CHIP.format(state=s, count=counts[s]))
        done, total = counts["実装完了"], len(scope)
        self.scope_lbl.configure(text=self.category or S.CAT_ALL)
        self.ratio_lbl.configure(text=S.RATIO.format(done=done, total=total, pct=round(100 * done / total) if total else 0))
        self.bar_counts = counts
        self._draw_bar()

    def _draw_bar(self) -> None:
        c = self.bar
        c.delete("all")
        w, h = c.winfo_width(), int(c.cget("height"))
        total = sum(self.bar_counts.values())
        if w <= 1 or not total:
            return
        x = 0.0
        for s in STATES:
            n = self.bar_counts.get(s, 0)
            if not n:
                continue
            x2 = x + w * n / total
            c.create_rectangle(round(x), 0, round(x2), h, fill=self.p["states"][s], width=0)
            x = x2

    def selected(self) -> list[ProjectStatus]:
        return [self.rows[i] for i in self.tree.selection() if i in self.rows]

    # ---------- 詳細 ----------
    def on_select(self) -> None:
        self._show_detail()
        self._update_edit()

    def _show_detail(self) -> None:
        sel = self.selected() if self.board else []
        for lb in (self.d_docs, self.d_impl, self.d_ev, self.d_hist):
            lb.delete(0, "end")
        self.d_impl_paths = []
        if len(sel) != 1:
            self.d_name.configure(text=S.DETAIL_MULTI.format(n=len(sel)) if sel else S.DETAIL_NONE)
            self.d_badge.pack_forget()
            for v in self.d_info.values():
                v.configure(text="")
            self._update_impl_buttons()
            return
        ps = sel[0]
        self.d_name.configure(text=ps.project.name)
        light_badge = ps.state == "証拠なし" and not self.p["dark"]
        self.d_badge.configure(text=ps.state, bg=self.p["states"].get(ps.state, self.p["muted"]),
                               fg=self.p["fg"] if light_badge else "#ffffff")
        self.d_badge.pack(anchor="w", pady=(self.px(6), self.px(10)), before=self.d_grid)
        info = {"source": G.source_text(ps), "where": ps.decided_by.get("path") or "-",
                "spec_dir": ps.project.spec_dir, "phase": G.phase_text(ps), "waiting": ps.waiting,
                "note": ps.folded.note or "-"}
        for k, v in self.d_info.items():
            v.configure(text=info[k])
        for doc in ps.project.docs:
            self.d_docs.insert("end", f"{doc.kind}  {doc.path}")
        for ip in ps.folded.impl:
            self.d_impl_paths.append(ip)
            self.d_impl.insert("end", ip.path if ip.exists_here else S.IMPL_MISSING.format(path=ip.path, pc=ip.pc))
            if not ip.exists_here:
                self.d_impl.itemconfig("end", fg=self.p["muted"])
        for ev in ps.evidence:
            line = S.EVIDENCE_LINE.format(source=S.SOURCE_LABELS.get(ev.source, ev.source), value=ev.value, where=ev.where)
            if ev.note:
                line += S.EVIDENCE_NOTE.format(note=ev.note)
            self.d_ev.insert("end", (S.EVIDENCE_CONFLICT if ev in ps.conflicts else "") + line)
        for rec in reversed(ps.folded.history[-20:]):
            self.d_hist.insert("end", G.history_line(rec))
        self._update_impl_buttons()

    def _update_impl_buttons(self) -> None:
        one = self.board is not None and len(self.selected()) == 1 and not self.busy
        cur = self.d_impl.curselection()
        ip = self.d_impl_paths[cur[0]] if cur and cur[0] < len(self.d_impl_paths) else None
        self.impl_open.configure(state="normal" if ip and ip.exists_here else "disabled")
        self.impl_add.configure(state="normal" if one else "disabled")
        self.impl_rm.configure(state="normal" if one and ip else "disabled")

    def _update_edit(self) -> None:
        n = len(self.selected()) if self.board else 0
        ok = n > 0 and not self.busy
        single = n == 1 and not self.busy
        for w in (self.e_state, self.e_wait):
            w.configure(state="readonly" if ok else "disabled")
        for w in (self.e_done, self.e_last, self.e_note):
            w.configure(state="normal" if single else "disabled")
        for w in (self.e_clear_note, self.e_copy):
            w.configure(state="normal" if single else "disabled")
        self.e_record.configure(state="normal" if ok else "disabled")
        self.e_undo.configure(state="normal" if self.undo_stack and self.board and not self.busy else "disabled")
        self._update_impl_buttons()

    # ---------- 開く ----------
    def open_board(self) -> None:
        if self.board:
            open_in_obsidian(self.root, os.path.abspath(resolve(self.vault, self.board.config["output"]["board"])))

    def open_primary(self) -> None:
        sel = self.selected()
        if sel:
            open_in_obsidian(self.root, sel[0].project.primary_doc.abs_path)

    def open_doc(self) -> None:
        sel, cur = self.selected(), self.d_docs.curselection()
        if len(sel) == 1 and cur:
            open_in_obsidian(self.root, sel[0].project.docs[cur[0]].abs_path)

    def open_impl(self) -> None:
        cur = self.d_impl.curselection()
        if not cur:
            return
        path = os.path.normpath(self.d_impl_paths[cur[0]].path)
        try:
            os.startfile(path)
        except OSError as ex:
            messagebox.showerror(S.WRITE_FAILED_TITLE, S.EXPLORER_FAILED.format(path=path, err=ex), parent=self.root)

    def copy(self) -> None:
        sel = self.selected()
        if len(sel) != 1 or not self.board:
            return
        template = self.board.config.get("gui", {}).get("copy_template") or S.DEFAULT_COPY_TEMPLATE
        self.root.clipboard_clear()
        self.root.clipboard_append(G.copy_text(template, sel[0]))
        before = self.gen_lbl.cget("text")
        self.gen_lbl.configure(text=S.COPIED.format(name=sel[0].project.name))
        self.root.after(3000, lambda: self.gen_lbl.configure(text=before))

    # ---------- 記録 ----------
    def record(self) -> None:
        sel = self.selected()
        if not sel or self.busy or not self.board:
            return
        fields, err = G.make_fields(self.e_state.get(), self.e_done.get(), self.e_last.get(),
                                    self.e_wait.get(), self.e_note.get(), multi=len(sel) > 1)
        if err:
            messagebox.showerror(S.WRITE_FAILED_TITLE, err, parent=self.root)
            return
        answer = True
        if len(sel) > 1:
            answer = messagebox.askyesno(S.CONFIRM_TITLE, G.confirm_text(len(sel), fields), parent=self.root)
        plan = G.bulk_plan(sel, fields, answer)
        if plan:
            self._write(plan, push_undo=True, clear_edit=True)

    def clear_note(self) -> None:
        sel = self.selected()
        if len(sel) == 1 and not self.busy:
            self._write(G.bulk_plan(sel, {"note": None}, True), push_undo=True)

    def add_impl(self) -> None:
        sel = self.selected()
        if len(sel) != 1 or self.busy:
            return
        path = filedialog.askdirectory(parent=self.root, title=S.IMPL_PICK, mustexist=True)
        if path:
            self._write(G.bulk_plan(sel, {"impl_add": [slash(os.path.abspath(path))]}, True), push_undo=True)

    def remove_impl(self) -> None:
        sel, cur = self.selected(), self.d_impl.curselection()
        if len(sel) == 1 and cur and not self.busy:
            self._write(G.bulk_plan(sel, {"impl_remove": [self.d_impl_paths[cur[0]].path]}, True), push_undo=True)

    def undo(self) -> None:
        if self.busy or not self.board:
            return
        if not self.undo_stack:
            messagebox.showinfo(S.UNDO_TITLE, S.UNDO_EMPTY, parent=self.root)
            return
        entry = self.undo_stack.pop()
        by_key = {ps.project.key: ps for ps in self.board.statuses}
        plan = [(by_key[k], f, {}) for k, f in entry if k in by_key and len(f) > 1]   # {'undo': True} だけは書かない
        if plan:
            self._write(plan, push_undo=False)
        else:
            self._update_edit()

    def _write(self, plan: list[tuple[ProjectStatus, dict, dict]], push_undo: bool, clear_edit: bool = False) -> None:
        """plan の行を write_mark で順に書き、書けたら build を1回。どちらも別スレッド。"""
        board, core = self.board, self.core

        def work():
            done, fail = [], None
            for ps, fields, back in plan:
                code, reason = core.write_mark(board, ps, fields, "user")
                if code != 0:
                    fail = (code, reason)
                    break
                done.append((ps.project.key, back))
            built = core.build(self.vault, self.config_path) if done else None
            return done, fail, built

        def finished(res, err):
            self._set_busy(False)
            if err is not None:
                messagebox.showerror(S.WRITE_FAILED_TITLE, str(err), parent=self.root)
                self.reload()
                return
            done, fail, built = res
            if push_undo and done:
                self.undo_stack.append(done)
            if clear_edit and done:
                self._clear_edit()
            if fail:
                msg = S.WRITE_FAILED.format(code=fail[0], reason=fail[1])
                if done:
                    msg += "\n" + S.WRITE_PARTIAL.format(done=len(done))
                messagebox.showerror(S.WRITE_FAILED_TITLE, msg, parent=self.root)
            if built is None:
                self._update_edit()
                return
            code, msg, new_board = built
            if code == 2:
                messagebox.showerror(S.BUILD_FAILED_TITLE, S.BUILD_FAILED.format(msg=msg), parent=self.root)
            if new_board is None:
                self.reload()
                return
            self.build_warn = msg if code == 3 else ""
            self._apply_board(new_board)

        self._run(work, finished)

    def _clear_edit(self) -> None:
        self.e_state.set(S.NO_CHANGE)
        self.e_wait.set(S.NO_CHANGE)
        for w in (self.e_done, self.e_last, self.e_note):
            w.delete(0, "end")


def _dpi_scale(root: tk.Tk) -> float:
    """DPI 対応を宣言した後は Tk が拡大しないので、システムの DPI に合わせて tk scaling を設定し、倍率を返す。"""
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except Exception:
        return 1.0
    root.tk.call("tk", "scaling", dpi / 72)
    return dpi / 96


def run(vault: str, config_path: str | None) -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root, vault, config_path)
    root.mainloop()
    return 0
