# ペースの見込み(pace.mark)と全体の見込み(pace.overall)。
from __future__ import annotations

from datetime import date

from specstatus import pace

from test_guilogic import ps, rec

DAY = date(2026, 10, 9)


def test_mark_median_and_eta():
    a = ps("A", "W/A", "着手済", done=4, last=7, history=[
        rec("2026-09-01T10:00:00+09:00", done_phase=0),
        rec("2026-09-03T10:00:00+09:00", done_phase=1),          # 2 日
        rec("2026-09-04T10:00:00+09:00", note="メモだけ"),
        rec("2026-09-13T10:00:00+09:00", done_phase=3),          # 10 日で 2 フェーズ = 5 日 ×2
        rec("2026-09-14T10:00:00+09:00", done_phase=4),          # 1 日
    ])
    pace.mark([a], DAY)
    assert a.pace == {"days_per_phase": 3.5, "remaining": 3, "eta_days": 10}   # 中央値(1, 2, 5, 5) = 3.5


def test_mark_none_cases():
    once = ps("B", "W/B", "着手済", done=1, last=3, history=[rec("2026-09-01T00:00:00+09:00", done_phase=1)])
    same = ps("C", "W/C", "着手済", done=1, last=3, history=[rec("2026-09-01T00:00:00+09:00", done_phase=1),
                                                         rec("2026-09-05T00:00:00+09:00", done_phase=1)])
    done = ps("D", "W/D", "実装完了", done=2, last=2, history=[rec("2026-09-01T00:00:00+09:00", done_phase=1),
                                                         rec("2026-09-05T00:00:00+09:00", done_phase=2)])
    nolast = ps("E", "W/E", "着手済", done=2, history=[rec("2026-09-01T00:00:00+09:00", done_phase=1),
                                                     rec("2026-09-05T00:00:00+09:00", done_phase=2)])
    pace.mark([once, same, done, nolast], DAY)
    assert once.pace is None and same.pace is None and done.pace is None
    assert nolast.pace == {"days_per_phase": 4.0, "remaining": None, "eta_days": None}


def test_overall():
    recent = ps("A", "W/A", "実装完了", source=("events", "実装完了"),
                history=[rec("2026-09-30T10:00:00+09:00", state="実装完了")])
    old = ps("B", "W/B", "実装完了", source=("events", "実装完了"),
             history=[rec("2026-06-01T10:00:00+09:00", state="実装完了")])
    left = [ps(n, f"W/{n}", s) for n, s in (("C", "未着手"), ("D", "着手済"), ("E", "一部未実装"))]
    out = pace.overall([recent, old, *left, ps("F", "W/F", "撤退")], DAY, weeks=2)
    assert (out["completed"], out["per_week"], out["remaining"], out["weeks_left"]) == (1, 0.5, 3, 6)
    assert "約 6 週" in out["text"] and "目安" in out["text"]
    none = pace.overall(left, DAY, weeks=8)
    assert none["weeks_left"] is None and "出せません" in none["text"]
