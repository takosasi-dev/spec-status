# 仕様書の本文から「未確定事項」の未回答の数と「撤退基準」の判定の時期を読み、ProjectStatus に付ける。
# 節は見出しの語で探す(番号は §12・§13 などと揺れる)。表の書き方の揺れは実物(2026-10-09)に合わせた。読むだけ。
from __future__ import annotations

import re
from typing import Callable

from .model import ProjectStatus
from .textutil import read_text

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
ROW_ID_RE = re.compile(r"^[A-Z]{1,3}-[A-Z]?\d+[a-z]?$")          # Q-1・U-3・Q-M1・R-2
PHASE_RE = re.compile(r"Phase\s*(\d+)")
BEFORE_RE = re.compile(r"開始前|開始時|の前|着手前")            # 「Phase 2 開始前」= Phase 1 を終えた所で判定
ANSWERED_RE = re.compile(r"回答済|解決済|^\s*\**解決|確定済|対応済|[(（]済[)）]")
OPEN_CELL_RE = re.compile(r"^\s*\**\s*(未|[?？—\-]?\s*$)")       # 状態の列: 未確認・未確定・未決・空・?・—
ANSWER_COLS = ("状態", "回答", "解決", "答え", "結論")             # 回答の済み・未を書く列(完全一致)
ASKEE_WORDS = ("回答者", "決める人", "誰が")                       # 回答者の列(部分一致)
MINE = "私"
DATE_COL_WORDS = ("判定", "時期", "期日")                          # 撤退基準の判定の期日の列(部分一致)
UNKNOWN_PHASE = "不明"
PHASE_LABEL_MAX = 20
FINISHED = ("実装完了", "撤退")                                    # 判定の時期を見ない状態


def section(lines: list[str], match: Callable[[str], bool]) -> list[str]:
    """見出しの文字が match に当たる最初の節の中身(見出しの行は含まない)。同じか浅い見出しで終わる。無ければ []。"""
    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln)
        if m and match(m.group(2)):
            level = len(m.group(1))
            out = []
            for ln2 in lines[i + 1:]:
                m2 = HEADING_RE.match(ln2)
                if m2 and len(m2.group(1)) <= level:
                    break
                out.append(ln2)
            return out
    return []


def table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """節の最初の表の (見出しの列, ID で始まる行の列)。区切りの行と ID の無い行は飛ばす。"""
    head: list[str] = []
    rows: list[list[str]] = []
    for ln in lines:
        s = ln.strip()
        if not s.startswith("|"):
            if head:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not head:
            head = cells
        elif ROW_ID_RE.match(row_id(cells)):
            rows.append(cells)
    return head, rows


def row_id(cells: list[str]) -> str:
    return cells[0].strip("~* ") if cells else ""


def _col(head: list[str], pred: Callable[[str], bool]) -> int | None:
    return next((i for i, h in enumerate(head) if pred(h.strip("* "))), None)


def _cell(cells: list[str], i: int | None) -> str:
    return cells[i] if i is not None and i < len(cells) else ""


def is_question_heading(h: str) -> bool:
    return "未確定事項" in h and "回答" not in h          # 「未確定事項への回答」は答えの節


def open_questions(lines: list[str]) -> list[tuple[list[str], bool]]:
    """未確定事項の表の、回答の済んでいない行の (列, 回答者が「私」か)。
    答えの列(状態・回答・解決)があればその値で、無ければ行の「回答済・解決済・(済)」と ID の取り消し線で見る。"""
    head, rows = table(section(lines, is_question_heading))
    ans = _col(head, lambda h: h in ANSWER_COLS)
    who = _col(head, lambda h: any(w in h for w in ASKEE_WORDS))
    out = []
    for cells in rows:
        text = " | ".join(cells)
        if "~~" in cells[0] or ANSWERED_RE.search(text) or (ans is not None and not OPEN_CELL_RE.match(_cell(cells, ans))):
            continue
        out.append((cells, _cell(cells, who).lstrip("* ").startswith(MINE)))
    return out


def judge_phase(text: str) -> int | None:
    """判定の期日の文字から、判定するときに終えているはずのフェーズ。読めなければ None。"""
    m = PHASE_RE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    return max(n - 1, 0) if BEFORE_RE.search(text[m.end():m.end() + 8]) else n


def _label(text: str) -> str:
    return re.split(r"[。(（]", text.replace("*", ""), maxsplit=1)[0].strip()[:PHASE_LABEL_MAX]


def retreat(lines: list[str], done_phase: int | None, finished: bool = False) -> dict | None:
    """撤退基準の表から {"due", "phase", "ids"}。表が無ければ None。
    due = 記録の done_phase が判定のフェーズでちょうど止まっている(先へ進んだ物は判定済みとみなす。終えた・撤退した物は False)。phase は判定の期日の文字
    (due なら一番後の期日、そうでなければ次に来る期日、読めなければ「不明」)。ids はその期日の行。"""
    head, rows = table(section(lines, lambda h: "撤退基準" in h))
    if not rows:
        return None
    col = _col(head, lambda h: any(w in h for w in DATE_COL_WORDS))
    dated = [(judge_phase(_cell(r, col)), _label(_cell(r, col)), row_id(r)) for r in rows]
    dated = [t for t in dated if t[0] is not None]
    if not dated:
        return {"due": False, "phase": UNKNOWN_PHASE, "ids": [row_id(r) for r in rows]}
    due = [t for t in dated if done_phase is not None and not finished and done_phase == t[0]]
    if due:
        last = max(due, key=lambda t: t[0])
        return {"due": True, "phase": last[1], "ids": [t[2] for t in due]}
    nxt = min(dated, key=lambda t: t[0])
    return {"due": False, "phase": nxt[1], "ids": [t[2] for t in dated if t[0] == nxt[0]]}


def doc_lines(ps: ProjectStatus, read: Callable[[str], str] = read_text) -> list[list[str]]:
    """仕様書の文書(付属を除く。主の文書が先)の行。読めない文書は飛ばす。"""
    docs = ps.project.spec_docs
    primary = ps.project.primary_doc
    out = []
    for d in [primary] + [d for d in docs if d is not primary]:
        try:
            out.append(read(d.abs_path).splitlines())
        except (OSError, UnicodeDecodeError):
            pass
    return out


def mark(statuses: list[ProjectStatus], read: Callable[[str], str] = read_text) -> None:
    """ps.questions(未回答があるときだけ)と ps.retreat(撤退基準の表があるときだけ)を付ける。"""
    for ps in statuses:
        texts = doc_lines(ps, read)
        qs = [q for lines in texts for q in open_questions(lines)]
        if qs:
            ps.questions = {"open": len(qs), "mine": sum(mine for _, mine in qs)}
        for lines in texts:
            r = retreat(lines, ps.done_phase, ps.state in FINISHED)
            if r:
                ps.retreat = r
                break
