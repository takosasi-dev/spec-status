# 記録漏れかも: 最後の記録より後の日に、実装フォルダの git のコミットか開発ログがある物に一言を付ける。
# 一覧ノートの「## 記録漏れかも(n)」の表も作る。読むだけ(git は history の関数で聞く)。
from __future__ import annotations

from datetime import datetime
from typing import Callable

from . import history
from .model import ProjectStatus

SKIP_STATES = ("撤退", "証拠なし")
EXPLAIN = "最後の記録より後の日に、実装フォルダの git のコミットか開発ログがある物。記録を1行足すと消える。"


def _md(day: str) -> str:
    return f"{day[5:7]}/{day[8:10]}"


def record_day(ps: ProjectStatus) -> str | None:
    """最後の記録の日(ローカルの日に直す)。"""
    r = ps.folded.last_record
    return datetime.fromisoformat(r.at).astimezone().date().isoformat() if r else None


def mark(statuses: list[ProjectStatus], git_date: Callable[[str], str | None] = history.git_last_date) -> None:
    """記録の日より日単位で後に git・開発ログがあれば ps.gap に「git 10/08・開発ログ 10/09 > 記録 10/05」。"""
    targets = [ps for ps in statuses if ps.folded.last_record and ps.state not in SKIP_STATES]
    gits = history.git_dates([p for ps in targets for p in history.impl_dirs(ps)], git_date)
    for ps in targets:
        rec = record_day(ps)
        git = max((d for d in (gits[p] for p in history.impl_dirs(ps)) if d), default=None)
        later = [f"{name} {_md(d)}" for name, d in (("git", git), ("開発ログ", ps.last_devlog_date)) if d and d > rec]
        if later:
            ps.gap = "・".join(later) + f" > 記録 {_md(rec)}"


def section(statuses: list[ProjectStatus], link: Callable[[ProjectStatus], str]) -> list[str]:
    """一覧ノートの「## 記録漏れかも(n)」の行。該当が無ければ []。"""
    rows = [ps for ps in statuses if ps.gap]
    if not rows:
        return []
    out = [f"## 記録漏れかも({len(rows)})", "", EXPLAIN, "", "| プロジェクト | 状態 | 動いた跡 |", "|---|---|---|"]
    return out + [f"| {link(ps)} | {ps.state} | {ps.gap} |" for ps in rows]
