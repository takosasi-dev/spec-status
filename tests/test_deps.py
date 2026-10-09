# 仕様書どうしの依存(deps)のテスト: 前提の節・依存と書き添えたリンクだけを見る、終わった物は出さない、循環、図。
from __future__ import annotations

from specstatus import deps as D

from test_guilogic import ps


def _read(texts):
    def read(p):
        if p not in texts:
            raise OSError("無い")
        return texts[p]
    return read


def test_dep_links_only_premise_and_dep_words():
    lines = """\
関連: [[Ref_仕様書]](形式の手本) / [[Core_仕様書|コア]](状態を決める側。依存) / [[Os]](OS非依存の話)
## 2. 前提(誤っていれば私に指摘すること)
- [[Base_仕様書#3 型]] の型を使う
## 3. 背景
- [[Other_仕様書]] を参考にした
""".splitlines()
    assert D.dep_links(lines) == ["Base_仕様書", "Core_仕様書"]


def test_mark_blocked_and_cycle():
    a, b, c = ps("A", "W/A", "着手済"), ps("B", "W/B", "着手済"), ps("C", "W/C", "実装完了")
    texts = {
        a.project.primary_doc.abs_path: "## 前提\n- [[B_仕様書]] と [[C_仕様書]] が要る\n- [[A_仕様書]] 自分\n",
        b.project.primary_doc.abs_path: "## 前提\n- [[a_仕様書]] が要る\n",          # 循環・大文字小文字
    }
    D.mark([a, b, c], read=_read(texts))
    assert a.blocked_by == ["B"]
    assert b.blocked_by == ["A"]
    assert c.blocked_by == []


def test_mermaid():
    a, b, c = ps("A", "W/A"), ps("B", "W/B"), ps('C"x', "W/C")
    a.blocked_by = ["B"]
    c.blocked_by = ["A", "B"]
    got = D.mermaid([a, b, c])
    assert got[:2] == ["```mermaid", "graph LR"] and got[-1] == "```"
    assert got[2] == '  n0["A"] --> n1["C#quot;x"]'
    assert got[3] == '  n2["B"] --> n1'
    assert got[4] == "  n2 --> n0"
    assert D.mermaid([b]) == []
