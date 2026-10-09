# ペースの見込み: 記録の done_phase が増えた時刻から 1 フェーズにかかった日数の中央値を出し、残りのフェーズの日数を見積もる。
# 全体は直近の週に実装完了になった数の週平均から、残りの本数が片付くまでの週数を出す(どちらも近似)。
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta

from .history import state_at
from .model import ProjectStatus

SKIP_STATES = ("実装完了", "撤退")      # もう進まない物は見積もらない
LEFT_STATES = ("未着手", "着手済", "一部未実装")


def _phase_days(ps: ProjectStatus) -> list[float]:
    """done_phase が増えるたびの、1 フェーズあたりの日数(2 フェーズ進んだら同じ値を 2 つ)。"""
    marks = []
    for r in ps.folded.history:
        dp = r.fields.get("done_phase")
        if isinstance(dp, int):
            try:
                marks.append((datetime.fromisoformat(r.at), dp))
            except ValueError:
                continue
    out: list[float] = []
    for (t0, d0), (t1, d1) in zip(marks, marks[1:]):
        if d1 > d0:
            out += [(t1 - t0).total_seconds() / 86400 / (d1 - d0)] * (d1 - d0)
    return out


def mark(statuses: list[ProjectStatus], today: date) -> None:
    """ps.pace = {days_per_phase, remaining, eta_days}。done_phase が増えた記録が無ければ None。
    最後のフェーズが分からなければ remaining と eta_days は None。"""
    for ps in statuses:
        ps.pace = None
        days = _phase_days(ps) if ps.state not in SKIP_STATES else []
        if not days:
            continue
        per = statistics.median(days)
        remaining = None
        if ps.last_phase is not None and ps.done_phase is not None:
            remaining = max(0, ps.last_phase - ps.done_phase)
        ps.pace = {"days_per_phase": round(per, 1), "remaining": remaining,
                   "eta_days": round(per * remaining) if remaining is not None else None}


def overall(statuses: list[ProjectStatus], today: date, weeks: int = 8) -> dict:
    """{weeks, completed, per_week, remaining, weeks_left, text}。直近 weeks 週に実装完了になった数の週平均で、
    残り(未着手・着手済・一部未実装)が片付く週数。完了が無ければ weeks_left は None。"""
    start = (today - timedelta(days=7 * weeks)).isoformat()
    completed = sum(ps.state == "実装完了" and state_at(ps, start) != "実装完了" for ps in statuses)
    remaining = sum(ps.state in LEFT_STATES for ps in statuses)
    per_week = completed / weeks if weeks else 0.0
    weeks_left = math.ceil(remaining / per_week) if per_week else None
    if weeks_left is None:
        text = f"直近 {weeks} 週に実装完了が無いので、見込みは出せません(残り {remaining} 本)"
    else:
        text = f"直近 {weeks} 週は週 {per_week:.1f} 本のペース。残り {remaining} 本は、このままなら約 {weeks_left} 週(目安)"
    return {"weeks": weeks, "completed": completed, "per_week": round(per_week, 2), "remaining": remaining,
            "weeks_left": weeks_left, "text": text}
