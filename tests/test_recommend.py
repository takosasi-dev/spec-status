# 今日のおすすめ(recommend)のテスト: 出さない物・点の順・理由・一覧ノートの行。
from __future__ import annotations

from datetime import date

from specstatus import recommend as R

from test_guilogic import ps, rec

TODAY = date(2026, 10, 9)


def test_excludes_and_order():
    done = ps("Done", "W/Done", "実装完了")                                  # 何も無い実装完了
    gone = ps("Gone", "W/Gone", "撤退", waiting="確認待ち")
    none = ps("None", "W/None", "証拠なし", waiting="確認待ち")
    wait = ps("Wait", "W/Wait", "着手済", waiting="確認待ち", history=[rec("2026-10-06T10:00:00+09:00")])
    vul = ps("Vul", "W/Vul", "実装完了")
    vul.vulns = {"count": 2, "worst": "重大"}
    part = ps("Part", "W/Part", "一部未実装")
    got = R.recommend([done, gone, none, wait, vul, part], TODAY)
    assert [p.project.name for p, _, _ in got] == ["Wait", "Vul", "Part"]
    assert got[0][2] == ["確認待ち(3日)"]
    assert got[0][1] == R.W_WAITING + 3 * R.W_WAITING_PER_DAY
    assert got[1][2] == ["脆弱な依存 2件(重大)"]
    assert got[1][1] == 2 * R.W_VULN_EACH + R.W_SEVERITY["重大"]


def test_reasons_and_tie_and_limit():
    a = ps("b", "W/b", "着手済")
    a.stale_days = 40
    a.spec_changed = "2026-10-05"
    b = ps("a", "W/a", "着手済")
    b.stale_days = 40
    b.spec_changed = "2026-10-05"
    got = R.recommend([a, b], TODAY, limit=1)
    assert [p.project.name for p, _, _ in got] == ["a"]                     # 同点は名前順
    assert got[0][2] == ["仕様が変わった(10-05)", "40日止まっている"]
    assert got[0][1] == R.W_SPEC_CHANGED + R.W_STALE_MAX * R.W_STALE_PER_DAY


def test_section_lines():
    p = ps("X", "W/X", "一部未実装", conflict=True)
    lines = R.section([p, ps("Y", "W/Y", "実装完了")], TODAY, lambda s: f"[[{s.project.name}]]")
    assert lines[0] == "## 今日のおすすめ(1)"
    assert lines[-1] == "| [[X]] | 一部未実装 | 一部未実装・食い違い |"
    assert R.section([], TODAY, str)[0] == "## 今日のおすすめ(0)"
