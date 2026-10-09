# tooltip_text(表の行の小窓の中身)のテスト。窓は出さない。
from __future__ import annotations

from test_guilogic import ps

from specstatus.tooltip import tooltip_text


def test_minimal_omits_empty_lines():
    p = ps("とても長い名前のプロジェクト", "Windows/x")
    assert tooltip_text(p) == "とても長い名前のプロジェクト\n状態: 証拠なし"


def test_full():
    p = ps("Alpha", "Windows/Alpha", "一部未実装", waiting="確認待ち", done=2, last=4)
    p.folded.note = "長いメモの全文。\n2行目"
    p.spec_changed = "2026-10-05"
    p.vulns = {"count": 1, "total": 3, "packages": ["lodash@4.17.0(GHSA-x)"], "worst": "HIGH"}
    p.stale_days, p.last_activity = 30, "2026-09-09"
    p.github = {"release": "v1.2.0"}
    p.project.docs[0].ac = (3, 5)
    assert tooltip_text(p).split("\n") == [
        "Alpha",
        "状態: 一部未実装",
        "待ち: 確認待ち",
        "Phase: 2/4",
        "受け入れ基準: 3/5",
        "メモ: 長いメモの全文。",
        "2行目",
        "仕様書の更新: 2026-10-05",
        "依存の脆弱性: 1 / 3 件(例: lodash@4.17.0)(一番重い: HIGH)",
        "止まっている: 30 日(最後に動いた日 2026-09-09)",
        "GitHub の版: v1.2.0",
    ]


def test_zero_vulns_and_no_release_hidden():
    p = ps("b", "Linux/b")
    p.vulns = {"count": 0, "total": 4, "packages": []}
    p.github = {"release": None}
    assert tooltip_text(p) == "b\n状態: 証拠なし"
