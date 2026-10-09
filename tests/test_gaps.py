# 記録漏れかも(gaps)のテスト: 日単位で後の git・開発ログ、対象外の状態、一覧ノートの表。git は差し替える。
from __future__ import annotations

from specstatus import gaps as G
from specstatus.model import ImplPath

from test_guilogic import ps, rec


def _with_impl(p, path):
    p.folded.impl = [ImplPath(path=path, pc="pc", exists_here=True)]
    return p


def test_mark_gap_git_and_devlog():
    a = _with_impl(ps("A", "W/A", "着手済", history=[rec("2026-10-05T10:00:00+09:00")]), "C:/w/a")
    a.last_devlog_date = "2026-10-09"
    b = _with_impl(ps("B", "W/B", "着手済", history=[rec("2026-10-08T23:00:00+09:00")]), "C:/w/b")
    b.last_devlog_date = "2026-10-08"                                      # 同じ日は漏れではない
    gits = {"C:/w/a": "2026-10-08", "C:/w/b": "2026-10-08"}
    calls = []

    def git(p):
        calls.append(p)
        return gits[p]

    G.mark([a, b], git_date=git)
    assert a.gap == "git 10/08・開発ログ 10/09 > 記録 10/05"
    assert b.gap is None
    assert sorted(calls) == ["C:/w/a", "C:/w/b"]


def test_mark_skips_and_local_day():
    none = ps("N", "W/N", "着手済")                                        # 記録が無い
    none.last_devlog_date = "2026-10-09"
    gone = ps("G", "W/G", "撤退", history=[rec("2026-10-01T10:00:00+09:00")])
    gone.last_devlog_date = "2026-10-09"
    G.mark([none, gone], git_date=lambda p: None)
    assert none.gap is None and gone.gap is None
    # UTC の 10/05 の夜は、ローカル(日本)では 10/06
    late = ps("L", "W/L", "着手済", history=[rec("2026-10-05T20:00:00+00:00")])
    late.last_devlog_date = "2026-10-06"
    day = G.record_day(late)
    G.mark([late], git_date=lambda p: None)
    assert (late.gap is None) == (day >= "2026-10-06")


def test_section():
    a = ps("A", "W/A", "着手済")
    a.gap = "git 10/08 > 記録 10/05"
    lines = G.section([a, ps("B", "W/B", "着手済")], lambda s: f"[[{s.project.name}]]")
    assert lines[0] == "## 記録漏れかも(1)"
    assert lines[-1] == "| [[A]] | 着手済 | git 10/08 > 記録 10/05 |"
    assert G.section([ps("B", "W/B")], str) == []
