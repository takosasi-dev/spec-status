# 概要の画面(dashboard)とカード表示(cards)の純関数のテスト: タイルの配置・名前の切り詰め・印・
# ドーナツの角度・分類ごとの完了率・今週動いた物・折れ線の座標。窓は出さない。
from __future__ import annotations

from datetime import date

from specstatus import cards, dashboard

from test_guilogic import ps, rec


# --- cards ---

def test_columns_for():
    assert cards.columns_for(0, 200, 10) == 1
    assert cards.columns_for(209, 200, 10) == 1
    assert cards.columns_for(210, 200, 10) == 1
    assert cards.columns_for(430, 200, 10) == 2
    assert cards.columns_for(1000, 200, 10) == 4


def test_grid_layout_fills_width():
    pos = cards.grid_layout(5, 430, 200, 90, 10)
    assert pos == [(10, 10, 200), (220, 10, 200), (10, 110, 200), (220, 110, 200), (10, 210, 200)]
    # 余りの幅はタイルを広げる(右端の余白は gap のまま)
    pos = cards.grid_layout(2, 500, 200, 90, 10)
    x, _, w = pos[1]
    assert w == 235 and x + w + 10 == 500
    assert cards.grid_layout(0, 500, 200, 90, 10) == []
    # 狭くても1列で、タイルは縮めない
    assert cards.grid_layout(1, 50, 200, 90, 10) == [(10, 10, 200)]


def test_truncate():
    m = len     # 1文字 = 1px とみなす
    assert cards.truncate("abcdef", 6, m) == "abcdef"
    assert cards.truncate("abcdef", 4, m) == "abc…"
    assert cards.truncate("abcdef", 1, m) == "…"
    assert cards.truncate("abcdef", 0, m) == "…"


def test_badges_and_phase_ratio():
    a = ps("A", "Windows/A", "着手済", waiting="確認待ち", done=2, last=4)
    a.vulns = {"count": 3, "total": 10}
    a.stale_days = 21
    a.spec_changed = "2026-10-01"
    a.project.docs[0].ac = (2, 5)
    assert cards.badges(a) == [("waiting", "確認待ち"), ("vuln", "脆弱 3"), ("stale", "止 21日"),
                               ("changed", "変"), ("ac", "AC 2/5")]
    assert cards.phase_ratio(a) == 0.5
    b = ps("B", "Windows/B")
    b.vulns = {"count": 0, "total": 4}
    assert cards.badges(b) == []
    assert cards.phase_ratio(b) is None
    assert cards.phase_ratio(ps("C", "W/C", done=7, last=5)) == 1.0
    assert cards.phase_ratio(ps("D", "W/D", done=0, last=0)) is None


# --- dashboard ---

def test_donut_segments():
    segs = dashboard.donut_segments({"実装完了": 1, "一部未実装": 0, "着手済": 3, "証拠なし": 0})
    assert segs == [("実装完了", 90.0, -90.0), ("着手済", 0.0, -270.0)]
    assert dashboard.donut_segments({}) == []
    segs = dashboard.donut_segments({s: 1 for s in ("実装完了", "一部未実装", "着手済", "未着手", "撤退", "証拠なし")})
    assert [s for s, _, _ in segs][0] == "実装完了" and abs(sum(e for _, _, e in segs) + 360) < 1e-9


def test_category_rates():
    sts = [ps("a", "Windows/ツール/a", "実装完了"), ps("b", "Windows/ツール/b"), ps("c", "Windows/ゲーム/c"),
           ps("d", "Linux/d", "実装完了")]
    assert dashboard.category_rates(sts) == [
        ("Windows", 1, 3), ("Windows/ツール", 1, 2), ("Linux", 1, 1), ("Windows/ゲーム", 0, 1)]
    assert dashboard.category_rates(sts, limit=2) == [("Windows", 1, 3), ("Windows/ツール", 1, 2)]


def test_this_week():
    today = date(2026, 10, 9)      # 金曜。週は 10-05(月)〜10-11(日)
    old = ps("old", "W/old", history=[rec("2026-10-04T23:00:00+09:00")])
    mon = ps("mon", "W/mon", history=[rec("2026-10-05T08:00:00+09:00")])
    thu = ps("thu", "W/thu", history=[rec("2026-09-01T00:00:00+09:00"), rec("2026-10-08T12:00:00+09:00")])
    none = ps("none", "W/none")
    got = dashboard.this_week([old, mon, none, thu], today)
    assert [p.project.name for p in got] == ["thu", "mon"]
    assert [p.project.name for p in dashboard.this_week([old, mon, thu], today, limit=1)] == ["thu"]


def test_chart_xy():
    assert dashboard.chart_xy([0, 5, 10], 0, 0, 100, 50, 10) == [0, 50, 50, 25, 100, 0]
    assert dashboard.chart_xy([3], 0, 0, 100, 50, 0) == [50, 50]


def test_recommend_missing_is_empty():
    # recommend が無くても・落ちても空で動く
    assert isinstance(dashboard._recommend([], date(2026, 10, 9)), list)
