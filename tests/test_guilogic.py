# GUI の純関数(guilogic)のテスト: 絞り込み・並べ替え・行の文字列(AC-39)、確認の後に書く物(AC-42)、
# 取り消しで戻す値(AC-43)。tkinter と core は使わない。型は model.py で直接組み立てる。
from __future__ import annotations

import json

from specstatus import guilogic as G
from specstatus.model import Doc, Folded, ImplPath, Project, ProjectStatus, Record


def rec(at: str, by: str = "user", pc: str = "pc", **kw) -> Record:
    fields = {"v": 1, "at": at, "pc": pc, "by": by, "doc": "d", "path": "p", **kw}
    return Record(fields=fields, file=f"{pc}.jsonl", line=1, raw=json.dumps(fields, ensure_ascii=False))


def ps(name: str, spec_dir: str, state: str = "証拠なし", *, waiting=None, conflict=False,
       done=None, last=None, history=(), source=("none", "")) -> ProjectStatus:
    doc = Doc(path=f"仕様書MDファイル/{spec_dir}/{name}_仕様書.md", abs_path=f"C:/v/{name}_仕様書.md",
              stem=f"{name}_仕様書", kind="仕様書", product=name, created=None, last_phase=None, spec_dir=spec_dir)
    proj = Project(key=f"{spec_dir}#{name}", name=name, spec_dir=spec_dir, docs=[doc])
    folded = Folded(waiting=waiting, done_phase=done, last_phase=last, history=list(history))
    return ProjectStatus(project=proj, state=state, decided_by={"source": source[0], "value": source[1], "path": ""},
                         evidence=[], conflicts=["x"] if conflict else [], folded=folded)


A = ps("Alpha", "Windows/ツール/Alpha", "実装完了", source=("setsumei", "実装完了"), done=3, last=5,
       history=[rec("2026-10-01T10:00:00+09:00", by="claude-code")])
B = ps("beta", "Linux/beta", "着手済", waiting="確認待ち", conflict=True, source=("events", "着手済"),
       history=[rec("2026-10-05T09:00:00+09:00")])
C = ps("Gamma", "Windows/ゲーム/Gamma", "証拠なし")
D = ps("delta", "OS非依存/delta", "未着手", waiting="実物待ち", done=1,
       history=[rec("2026-10-03T00:00:00+00:00")])
ALL = [A, B, C, D]


def names(rows):
    return [r.project.name for r in rows]


# --- AC-39 絞り込み ---

def test_filter_none_keeps_order():
    assert names(G.filter_rows(ALL, set(), None, False, False, "")) == ["Alpha", "beta", "Gamma", "delta"]


def test_filter_states_any_of():
    assert names(G.filter_rows(ALL, {"実装完了", "未着手"}, None, False, False, "")) == ["Alpha", "delta"]


def test_filter_os():
    assert names(G.filter_rows(ALL, set(), "Windows", False, False, "")) == ["Alpha", "Gamma"]
    assert names(G.filter_rows(ALL, set(), "Win", False, False, "")) == []
    assert names(G.filter_rows(ALL, set(), "Windows/ゲーム", False, False, "")) == ["Gamma"]


def test_category_tree():
    # 2段目は3段以上ある仕様書フォルダだけ(Linux/beta の beta は分類にしない)
    assert G.category_tree(ALL) == [
        ("Linux", "", "Linux", 1, 0),
        ("OS非依存", "", "OS非依存", 1, 0),
        ("Windows", "", "Windows", 2, 1),
        ("Windows/ゲーム", "Windows", "ゲーム", 1, 0),
        ("Windows/ツール", "Windows", "ツール", 1, 1),
    ]


def test_filter_waiting_and_conflict():
    assert names(G.filter_rows(ALL, set(), None, True, False, "")) == ["beta", "delta"]
    assert names(G.filter_rows(ALL, set(), None, False, True, "")) == ["beta"]


def test_filter_query_name_and_folder_casefold():
    assert names(G.filter_rows(ALL, set(), None, False, False, "ALPHA")) == ["Alpha"]
    assert names(G.filter_rows(ALL, set(), None, False, False, "ゲーム")) == ["Gamma"]
    assert names(G.filter_rows(ALL, set(), None, False, False, "  ")) == names(ALL)


def test_filter_combined():
    assert names(G.filter_rows(ALL, {"着手済", "未着手"}, None, True, True, "be")) == ["beta"]


# --- AC-39 並べ替え ---

def test_sort_each_column_both_ways():
    exp = {
        "state": ["Alpha", "beta", "delta", "Gamma"],
        "name": ["Alpha", "beta", "delta", "Gamma"],
        "spec_dir": ["beta", "delta", "Gamma", "Alpha"],   # Linux < OS非依存 < Windows/ゲーム < Windows/ツール
        "phase": ["delta", "Alpha", "beta", "Gamma"],
        "waiting": ["Alpha", "Gamma", "beta", "delta"],
        "last": ["Alpha", "delta", "beta", "Gamma"],         # 10-03T00:00Z = 09:00+09 < 10-05
        "conflict": ["Alpha", "Gamma", "delta", "beta"],
    }
    for col, order in exp.items():
        assert names(G.sort_rows(ALL, col, False)) == order, col
    # 降順は値の順が逆。同じ値どうしは元の並び(安定)
    assert names(G.sort_rows(ALL, "name", True)) == ["Gamma", "delta", "beta", "Alpha"]
    assert names(G.sort_rows(ALL, "conflict", True)) == ["beta", "Alpha", "Gamma", "delta"]
    assert names(G.sort_rows(ALL, "source", False))[0] == "Gamma"   # なし < 記録 < 説明書(fold 順)


# --- 行の文字列(§9.5 の約束) ---

def test_row_values():
    assert G.row_values(A) == ("実装完了", "Alpha", "Windows/ツール/Alpha", "3/5", "なし",
                               "2026-10-01(Claude Code)", "説明書: 実装完了", "", "")
    assert G.row_values(B)[3:] == ("-", "確認待ち", "2026-10-05(私)", "記録: 着手済", "!", "")
    assert G.row_values(C)[5:7] == ("", "なし")
    assert G.row_values(D)[3] == "1/?"


def test_count_by_state():
    c = G.count_by_state(ALL)
    assert list(c) == ["実装完了", "一部未実装", "着手済", "未着手", "撤退", "証拠なし"]
    assert c == {"実装完了": 1, "一部未実装": 0, "着手済": 1, "未着手": 1, "撤退": 0, "証拠なし": 1}


# --- AC-42 確認の後に書く物 ---

def test_make_fields_multi_only_state_and_waiting():
    f, err = G.make_fields("着手済", "2", "5", "変えない", "メモ", multi=True)
    assert err is None and f == {"state": "着手済"}
    assert G.make_fields("変えない", "", "", "変えない", "", multi=True) == ({}, G.S.ERR_NO_FIELDS)


def test_make_fields_single():
    f, err = G.make_fields("変えない", " 2 ", "", "実物待ち", "次は §8.5", multi=False)
    assert err is None and f == {"done_phase": 2, "waiting": "実物待ち", "note": "次は §8.5"}
    assert G.make_fields("変えない", "x", "", "変えない", "", multi=False)[1]
    assert G.make_fields("変えない", "100", "", "変えない", "", multi=False)[1]
    assert G.make_fields("変えない", "", "", "変えない", "a" * 201, multi=False)[1]


def test_bulk_plan_yes_writes_n_no_writes_zero():
    fields = {"state": "撤退", "waiting": "なし"}
    sel = [A, B, C]
    plan = G.bulk_plan(sel, fields, True)
    assert [p[0] for p in plan] == sel and all(p[1] == fields for p in plan)
    assert G.bulk_plan(sel, fields, False) == []
    msg = G.confirm_text(3, {"state": "撤退"})
    assert "3 件" in msg and "撤退" in msg and "変えない" in msg


# --- AC-43 取り消しで戻す値 ---

def test_undo_state_none_becomes_null():
    assert G.undo_fields(Folded(), {"state": "着手済"}) == {"state": None, "undo": True}
    assert G.undo_fields(Folded(state="未着手"), {"state": "着手済"}) == {"state": "未着手", "undo": True}


def test_undo_other_fields():
    before = Folded(done_phase=1, last_phase=None, waiting=None, note="前のメモ")
    got = G.undo_fields(before, {"done_phase": 2, "last_phase": 4, "waiting": "確認待ち", "note": "新"})
    assert got == {"done_phase": 1, "last_phase": None, "waiting": "なし", "note": "前のメモ", "undo": True}
    assert G.undo_fields(Folded(), {"note": None}) == {"note": None, "undo": True}


def test_undo_impl_swaps_add_and_remove():
    before = Folded(impl=[ImplPath(path="L:/x/Old", pc="pc", exists_here=True)])
    assert G.undo_fields(before, {"impl_add": ["L:/x/New"]}) == {"impl_remove": ["L:/x/New"], "undo": True}
    assert G.undo_fields(before, {"impl_remove": ["l:/X/old"]}) == {"impl_add": ["l:/X/old"], "undo": True}
    # 前から結ばれていた物を足した記録は、取り消しても外さない
    assert G.undo_fields(before, {"impl_add": ["L:/x/Old/"]}) == {"undo": True}


def test_bulk_undo_each_project_its_own_before():
    plan = G.bulk_plan([A, D], {"waiting": "なし"}, True)
    assert [p[2] for p in plan] == [{"waiting": "なし", "undo": True}, {"waiting": "実物待ち", "undo": True}]


# --- その他 ---

def test_copy_text_and_history_line():
    assert G.copy_text("仕様書: {abs_path}", A) == "仕様書: C:/v/Alpha_仕様書.md"
    r = rec("2026-10-05T09:00:00+09:00", by="user", pc="pc2", state=None, impl_add=["L:/a"], undo=True)
    line = G.history_line(r)
    assert line.startswith("2026-10-05T09:00:00+09:00  私  pc2  ")
    assert "状態=(消す)" in line and "フォルダを足す=L:/a" in line and line.endswith("取り消し")


# --- v0.7.0: 新しい欄・絞り込み中の表示・記録した直後の一言・記録のフォルダの変化 ---

def test_extra_details_empty_and_zero_hidden():
    p = ps("e", "Linux/e")
    assert G.extra_details(p) == {}
    p.questions = {"open": 0, "mine": 0}
    p.retreat = {"due": False, "phase": "Phase 0", "ids": ["R-1"]}
    p.pace = {"days_per_phase": 3.0, "remaining": 0, "eta_days": 0}
    p.eol = {"runtimes": [{"name": "python", "version": "3.12", "eol": "2028-10-31", "ended": False}], "outdated": []}
    p.github = {"release": "v1", "stars": None, "forks": None, "downloads": None}
    assert G.extra_details(p) == {}


def test_extra_details_all():
    p = ps("f", "Linux/f")
    p.gap = "git 10/08・開発ログ 10/09 > 記録 10/05"
    p.questions = {"open": 3, "mine": 2}
    p.retreat = {"due": True, "phase": "Phase 0", "ids": ["R-1"]}
    p.blocked_by = ["A", "B"]
    p.pace = {"days_per_phase": 4.6, "remaining": 3, "eta_days": 13.8}
    p.eol = {"runtimes": [{"name": "node", "version": "16", "eol": "2023-09-11", "ended": True}],
             "outdated": [{"package": "x", "version": "1", "latest": "3", "behind": 2}] * 3}
    p.github = {"stars": 12, "forks": 0, "downloads": None}
    assert G.extra_details(p) == {
        "gap": "git 10/08・開発ログ 10/09 > 記録 10/05",
        "questions": "3(あなたの番 2)",
        "retreat": "Phase 0",
        "blocked_by": "A・B",
        "pace": "残り 3 フェーズ ≒ 14 日",
        "eol": "サポート切れ 1・遅れている依存 3",
        "gh_stats": "スター 12・フォーク 0",
    }
    p.questions = {"open": 1, "mine": 0}
    assert G.extra_details(p)["questions"] == "1"


def test_extra_fields_shown_in_detail():
    from specstatus import strings as S
    keys = [k for k, _ in S.DETAIL_FIELDS]
    for k, _ in S.EXTRA_FIELDS:
        assert k in keys and k in S.DETAIL_HIDE_EMPTY


def test_filter_summary():
    assert G.filter_summary([], None, [], "  ") == ""
    assert G.filter_summary(["着手済"], "Windows", ["待ち"], "") == "絞り込み中: 着手済・Windows・待ち"
    assert G.filter_summary([], None, [], "is:脆弱") == "絞り込み中: 検索「is:脆弱」"
    assert G.filter_summary([], None, [], "あ" * 25) == "絞り込み中: 検索「" + "あ" * 20 + "…」"


def test_flash_text():
    assert G.flash_text(["Alpha"], {"state": "着手済"}) == "Alphaを着手済にしました(Ctrl+Z で戻す)"
    assert G.flash_text(["a", "b", "c"], {"state": "実装完了", "waiting": "なし"}).startswith("3 件を実装完了に")
    assert G.flash_text(["a"], {"waiting": "確認待ち"}).startswith("aの待ちを確認待ちに")
    assert G.flash_text(["a"], {"note": "メモ"}).startswith("aのメモを記録")
    assert G.flash_text(["a"], {"note": None}).startswith("aのメモを消し")
    assert G.flash_text(["a"], {"impl_add": ["L:/x"]}).startswith("aに実装フォルダを足し")
    assert G.flash_text(["a"], {"impl_remove": ["L:/x"]}).startswith("aから実装フォルダを外し")
    assert G.flash_text(["a"], {"done_phase": 2}).startswith("aに記録しました")


def test_events_stamp(tmp_path):
    d = tmp_path / "events"
    assert G.events_stamp(str(d)) == (0.0, 0, 0)          # フォルダがまだ無い
    d.mkdir()
    (d / "pc.jsonl").write_bytes(b"{}\n")
    (d / ".pc.lock").write_text("x", encoding="utf-8")    # 記録でない物は数えない
    first = G.events_stamp(str(d))
    assert first[1:] == (1, 3)
    assert G.events_stamp(str(d)) == first
    with open(d / "pc.jsonl", "ab") as f:
        f.write(b"{}\n")
    assert G.events_stamp(str(d)) != first                 # 時刻の細かさが粗くても大きさで分かる
    (d / "pc2.jsonl").write_text("", encoding="utf-8")
    assert G.events_stamp(str(d))[1] == 2
