# 仕様書の未確定事項・撤退基準の読み取り(specinfo)のテスト: 見出しの番号の揺れ、答えの列の有無、判定の期日。
from __future__ import annotations

from specstatus import specinfo as S

from test_guilogic import ps, rec

SPEC = """\
## 12. 実装フェーズ
| Phase | 内容 |
|---|---|
| 0 | 実物を集める |

### 撤退基準(C-11)

| # | 条件 | 判定期日 |
|---|---|---|
| R-1 | 使えなければ捨てる | Phase 0 完了時 |
| R-2 | 遅ければ捨てる | Phase 3 開始前 |
| R-3 | 誰も使わなければ畳む | 導入から30日 |

## 13. 未確定事項(実装前に確認が必要)

| # | 内容 | 回答者 |
|---|---|---|
| Q-1 | 名前は仮称 | 私 |
| Q-2 | 動くか。**未確認** | 実測 |
| Q-3 | 置き場所。**回答済(2026-10-02)**: L: の下 | 私 |
| ~~Q-4~~ | **解決（v1.5）**: 戻す | — |
| Q-5 | 公開するか | 私(§8) |
| Q-6 | 決めた | 私(済) |

## 14. 変更履歴
| Q-9 | 表の外の行は数えない | 私 |
"""


def _lines(s: str = SPEC) -> list[str]:
    return s.splitlines()


def test_open_questions_without_answer_column():
    got = S.open_questions(_lines())
    assert [c[0] for c, _ in got] == ["Q-1", "Q-2", "Q-5"]
    assert [m for _, m in got] == [True, False, True]


def test_open_questions_with_status_column_and_other_heading():
    text = """\
## 10. Claude Code実装時の確認事項(未確定事項)
| # | 内容 | 状態 | 回答者 |
|---|---|---|---|
| Q-1 | a | 未確認 | 私 |
| Q-2 | b | 確定(D-3) | 私 |
| Q-3 | c | | 実装者 |
| Q-4 | d | ? | 私 |
## 未確定事項への回答(10-02、依頼者)
| Q-5 | e | 未確認 | 私 |
"""
    got = S.open_questions(text.splitlines())
    assert [c[0] for c, _ in got] == ["Q-1", "Q-3", "Q-4"]
    assert sum(m for _, m in got) == 2


def test_retreat_due_and_phase_label():
    lines = _lines()
    assert S.retreat(lines, None) == {"due": False, "phase": "Phase 0 完了時", "ids": ["R-1"]}
    assert S.retreat(lines, 0) == {"due": True, "phase": "Phase 0 完了時", "ids": ["R-1"]}
    # 「Phase 3 開始前」は Phase 2 を終えた所で判定。先へ進んだ R-1 は判定済みとみなす
    assert S.retreat(lines, 2) == {"due": True, "phase": "Phase 3 開始前", "ids": ["R-2"]}
    assert S.retreat(lines, 1)["due"] is False
    assert S.retreat(lines, 5, finished=True)["due"] is False


def test_retreat_unknown_and_missing():
    text = "### 撤退基準\n| # | 条件 |\n|---|---|\n| R-1 | 使わなければ捨てる |\n"
    assert S.retreat(text.splitlines(), 3) == {"due": False, "phase": "不明", "ids": ["R-1"]}
    assert S.retreat(["## 1. 目的"], 3) is None


def test_mark_sets_fields():
    a = ps("A", "W/A", "着手済", done=0, history=[rec("2026-10-01T10:00:00+09:00", done_phase=0)])
    b = ps("B", "W/B", "実装完了", done=3)
    c = ps("C", "W/C", "未着手")
    texts = {a.project.primary_doc.abs_path: SPEC, b.project.primary_doc.abs_path: SPEC}

    def read(p):
        if p not in texts:
            raise OSError("無い")
        return texts[p]

    S.mark([a, b, c], read=read)
    assert a.questions == {"open": 3, "mine": 2}
    assert a.retreat == {"due": True, "phase": "Phase 0 完了時", "ids": ["R-1"]}
    assert b.retreat["due"] is False                      # 実装完了は判定の時期を見ない
    assert c.questions is None and c.retreat is None


def test_section_stops_at_same_level():
    lines = ["## A 前提", "x", "### 子", "y", "## B", "z"]
    assert S.section(lines, lambda h: "前提" in h) == ["x", "### 子", "y"]
