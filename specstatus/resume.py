# 再開の指示文: Claude Code に貼ると、仕様書の続き(次のフェーズ・未チェックの受け入れ基準・未回答の未確定事項・
# 記録の後の仕様の差分)から作業を始められる文を作る。読むだけ(仕様書と、snapshots の写し)。
from __future__ import annotations

import re
from typing import Callable

from . import snapshots
from .find import AC_RE
from .model import ProjectStatus
from .specinfo import HEADING_RE, doc_lines, open_questions, section
from .textutil import read_text

FIRST_LINE = "次の仕様書の続きを実装して。着手する前に SpecStatus の show で状態を確かめること。"
PHASE_BODY_LINES = 5        # 次のフェーズの見出しの後に入れる中身の行
AC_MAX = 10                 # 未チェックの受け入れ基準の行の上限(後ろの段が切られないように)
QUESTION_MAX = 8            # 未回答の未確定事項の行の上限
CUT = "(長いので切りました。残りは仕様書を直接読んでください)"


def next_phase(lines: list[str], n: int) -> list[str]:
    """「実装フェーズ」の節から Phase n の行: 表の行(1列目が n)と、「### Phase n」の見出しと中身の数行。"""
    sec = section(lines, lambda h: "実装フェーズ" in h)
    out = [ln.strip() for ln in sec if re.match(rf"^\|\s*(Phase\s*)?{n}\s*\|", ln.strip())]
    for i, ln in enumerate(sec):
        if HEADING_RE.match(ln) and re.search(rf"Phase\s*{n}(?!\d)", ln):
            body = []
            for ln2 in sec[i + 1:]:
                if HEADING_RE.match(ln2):
                    break
                if ln2.strip():
                    body.append(ln2.rstrip())
            out += [ln.strip()] + body[:PHASE_BODY_LINES]
            break
    return out


def prompt(ps: ProjectStatus, max_lines: int = 40, read: Callable[[str], str] = read_text,
           folder: str | None = None) -> str:
    """Claude Code に貼る再開の指示。max_lines を超える分は後ろの段から切る。"""
    texts = doc_lines(ps, read)
    done = ps.done_phase
    nxt = 0 if done is None else done + 1
    head = [FIRST_LINE, "", f"仕様書: {ps.project.primary_doc.abs_path}",
            f"状態: {ps.state} / 待ち: {ps.waiting} / 終えたフェーズ: {'-' if done is None else done}"
            + (f"(全 {ps.last_phase})" if ps.last_phase is not None else "")]
    if ps.folded.note:
        head.append(f"最後のメモ: {ps.folded.note}")

    phase = next((p for lines in texts if (p := next_phase(lines, nxt))), [])
    acs = [ln.strip() for lines in texts for ln in lines if (m := AC_RE.match(ln)) and m.group(1) == " "]
    qs = ["| " + " | ".join(cells) + " |" for lines in texts for cells, _ in open_questions(lines)]
    diff = snapshots.diff_prompt(ps, folder).splitlines()
    more = "(ほかは仕様書を直接読んでください)"
    parts = [(f"次のフェーズ(Phase {nxt}):", phase),
             (f"まだチェックの付いていない受け入れ基準({len(acs)}):", acs[:AC_MAX] + ([more] if len(acs) > AC_MAX else [])),
             (f"まだ回答の無い未確定事項({len(qs)}):", qs[:QUESTION_MAX] + ([more] if len(qs) > QUESTION_MAX else [])),
             ("記録した後に仕様書が変わった所:", diff)]

    out = head
    for title, body in parts:
        room = max_lines - len(out) - 2          # 空行と題の分
        if not body or room <= 0:
            continue
        out += ["", title] + body[:room]
        if len(body) > room:
            out[-1] = CUT
    return "\n".join(out[:max_lines]) + "\n"
