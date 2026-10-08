# 証拠の読み手5本(specstatus/evidence)の単体テスト。AC-10〜AC-12 の読み手側。
# 合成の一時フォルダ(tmp_path)だけを使い、本物の vault・L: には触らない。
from __future__ import annotations

import pytest

from specstatus.evidence import devlog, handoff, implroot, setsumei, tooldeck
from specstatus.model import Doc, Project


def proj(name: str, spec_dir: str = "Windows/Claude・開発ツール/X", aliases=()) -> Project:
    d = Doc(path=f"仕様書MDファイル/{spec_dir}/{name}_仕様書.md", abs_path="", stem=f"{name}_仕様書",
            kind="仕様書", product=name, created=None, last_phase=None, spec_dir=spec_dir)
    return Project(key=f"{spec_dir}#{name}", name=name, spec_dir=spec_dir, docs=[d], aliases=list(aliases))


def write(path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


MAP = {"実装完了": "実装完了", "一部未実装": "一部未実装", "導入済み": "実装完了"}


# ---- FR-15 / AC-11: 空のパスは読まない、書いてあって無ければ例外 ----

@pytest.mark.parametrize("mod,sec", [
    (setsumei, {"dir": ""}),
    (tooldeck, {"toml": ""}),
    (implroot, {"roots": []}),
    (handoff, {"handoffstub_toml": "", "memo_dir": "引き続きメモ"}),
    (devlog, {"dir": ""}),
])
def test_empty_path_is_not_configured(mod, sec):
    assert mod.configured("V", sec) is False


@pytest.mark.parametrize("mod,sec", [
    (setsumei, {"dir": "無い"}),
    (tooldeck, {"toml": "無い/tools.toml"}),
    (implroot, {"roots": ["無い"]}),
    (handoff, {"handoffstub_toml": "無い.toml", "memo_dir": "m"}),
    (devlog, {"dir": "無い"}),
])
def test_missing_path_raises(tmp_path, mod, sec):
    assert mod.configured(str(tmp_path), sec) is True
    with pytest.raises(OSError):
        mod.read(str(tmp_path), sec, [proj("A")])


def test_names_and_sources():
    for mod in (setsumei, tooldeck, implroot, handoff, devlog):
        assert mod.NAME == mod.__name__.rsplit(".", 1)[-1]


# ---- setsumei (FR-9) ----

def test_setsumei(tmp_path):
    d = tmp_path / "説明書"
    write(d / "GapCheck.md", "---\ntags:\n  - x\n状態: 実装完了\n作成日: 2026-09-17\n---\n# GapCheck — 秘密の本文\n")
    write(d / "hook.md", "---\n状態: 導入済み\n---\n")
    write(d / "Odd.md", "---\n状態: 謎の値\n---\n")
    write(d / "NoState.md", "---\n作成日: 2026-09-17\n---\n")
    write(d / "Broken.md", "---\n状態: 実装完了\n本文\n")
    ps = [proj("gapcheck"), proj("Hook"), proj("Odd"), proj("NoState"), proj("Broken"), proj("Nothing")]
    r = setsumei.read(str(tmp_path), {"dir": "説明書", "map": MAP}, ps)
    ev = r.found["Windows/Claude・開発ツール/X#gapcheck"][0]
    assert (ev.source, ev.state, ev.value) == ("setsumei", "実装完了", "実装完了")
    assert ev.where.endswith("説明書/GapCheck.md") and "\\" not in ev.where
    assert r.found["Windows/Claude・開発ツール/X#Hook"][0].state == "実装完了"
    odd = r.found["Windows/Claude・開発ツール/X#Odd"][0]
    assert (odd.state, odd.value, odd.note) == (None, "謎の値", "写し方の無い値")
    assert set(r.found) == {p.key for p in ps[:3]}
    assert [u.path.rsplit("/", 1)[-1] for u in r.unreadable] == ["Broken.md"]
    assert r.unreadable[0].reader == "setsumei"
    assert "秘密の本文" not in repr(r)


def test_setsumei_same_name_two_projects(tmp_path):
    write(tmp_path / "s" / "VaultDoctor.md", "---\n状態: 一部未実装\n---\n")
    a, b = proj("VaultDoctor", "Windows/Claude・開発ツール/VaultDoctor"), proj("VaultDoctor", "OS非依存/Obsidianプラグイン/VaultDoctor")
    r = setsumei.read(str(tmp_path), {"dir": str(tmp_path / "s"), "map": MAP}, [a, b])
    assert set(r.found) == {a.key, b.key}


# ---- tooldeck (FR-10) / AC-10 の読み手側 ----

TOOLS = '''
[[tool]]
id = "GapCheck"
state = "実装完了"
  [[tool.command]]
  id = "show"
[[tool]]
id = "MonthlyReport"
state = "一部未実装"
[[tool]]
id = "Weird"
state = "検討中"
'''


def test_tooldeck(tmp_path):
    write(tmp_path / "td" / "tools.toml", TOOLS)
    ps = [proj("gapcheck"), proj("MonthlyReport"), proj("Weird"), proj("show"), proj("Other")]
    r = tooldeck.read(str(tmp_path), {"toml": "td/tools.toml", "map": MAP}, ps)
    assert r.found[ps[0].key][0].state == "実装完了"
    assert r.found[ps[1].key][0].state == "一部未実装"
    w = r.found[ps[2].key][0]
    assert (w.state, w.value, w.note) == (None, "検討中", "写し方の無い値")
    assert set(r.found) == {ps[0].key, ps[1].key, ps[2].key}   # [[tool.command]] の id は拾わない
    assert r.found[ps[0].key][0].where.endswith("td/tools.toml")


def test_tooldeck_broken_toml_raises(tmp_path):
    write(tmp_path / "tools.toml", "[[tool]\nid = ")
    with pytest.raises(Exception):
        tooldeck.read(str(tmp_path), {"toml": "tools.toml", "map": MAP}, [proj("A")])


# ---- implroot (FR-11) ----

def test_implroot(tmp_path):
    root = tmp_path / "root"
    write(root / "GapCheck" / "NOTES.md", "x")
    (root / "NoMarker").mkdir()
    (root / "GapCheckX").mkdir()
    ps = [proj("gapcheck"), proj("NoMarker"), proj("GapChe")]
    r = implroot.read(str(tmp_path), {"roots": [str(root)], "markers": ["NOTES.md"]}, ps)
    assert list(r.found) == [ps[0].key]
    ev = r.found[ps[0].key][0]
    assert (ev.source, ev.state) == ("implroot", "着手済")
    assert ev.value.endswith("root/GapCheck") and "\\" not in ev.value

    r = implroot.read(str(tmp_path), {"roots": ["root"], "markers": []}, ps)
    assert set(r.found) == {ps[0].key, ps[1].key}


# ---- handoff (FR-12) / AC-12 ----

HS = '''
[paths]
memo_dir = 'ignored'
[map]
'ToolDeck'      = 'ToolDeck'
'Started'       = 'Started'
'Todo'          = 'Todo'
'OS非依存/Dup'  = 'DupRel'
'Dup'           = 'DupName'
'Excluded'      = ''
'NoMemo'        = 'NoSuchMemo'
'''


def test_handoff_ac12(tmp_path):
    write(tmp_path / "hs.toml", HS)
    m = tmp_path / "メモ"
    write(m / "Started.md", "# Started 引き継ぎメモ\n\n本文\n")
    write(m / "Todo.md", "# Todo\n\n状態:  未着手 \n起票: 2026-10-01\n")
    write(m / "ToolDeck.md", "# ToolDeck\n\n最終更新: 2026-09-21\n状態: **実装完了・依頼者の手動確認待ち**。秘密\n")
    write(m / "DupRel.md", "x\n")
    write(m / "DupName.md", "  状態: 未着手\n")   # 行頭でない
    write(m / "Excluded.md", "x\n")
    ps = [proj("S", "A/Started"), proj("T", "B/Todo"), proj("TD", "Windows/Claude・開発ツール/ToolDeck"),
          proj("D1", "OS非依存/Dup"), proj("D2", "Android/Dup"), proj("E", "C/Excluded"),
          proj("N", "C/NoMemo"), proj("U", "C/Unlisted")]
    r = handoff.read(str(tmp_path), {"handoffstub_toml": "hs.toml", "memo_dir": "メモ"}, ps)
    st = {k.split("#")[1]: [(e.state, e.value) for e in v] for k, v in r.found.items()}
    assert st["S"][0][0] == "着手済"
    assert st["T"] == [("未着手", "未着手")]
    assert st["TD"][0][0] == "着手済"                 # `状態: **実装完了…**` の行は使わない
    assert st["D1"][0][1].endswith("DupRel.md")       # 相対パスのキーが優先
    assert st["D2"][0] == ("着手済", st["D2"][0][1]) and st["D2"][0][1].endswith("DupName.md")
    assert set(st) == {"S", "T", "TD", "D1", "D2"}    # "" ・メモ無し・未登録は証拠なし
    assert r.found[ps[1].key][0].where.endswith("Todo.md#L3")
    assert "秘密" not in repr(r)


# ---- devlog (FR-13) / AC-12 ----

def test_devlog_ac12(tmp_path):
    d = tmp_path / "開発ログ"
    write(d / "2026-10-05.md", "# 2026-10-05 開発ログ\n### 🕒 [10:00] VaultDoctor を直した\n")
    write(d / "2026-10-07.md", "### VaultDoctorX\n本文に VaultDoctor\n")
    write(d / "2026-10-01.md", "### vaultdoctor の古い記録\n")
    write(d / "2026-10-08.md", "### 🕒 [02:55] DBC(旧 SvcScope): 名前を決めた\n### SpecLint を直した\n## Other\n")
    write(d / "_旧ログ" / "2026-10-09.md", "### VaultDoctor\n")
    write(d / "メモ.md", "### VaultDoctor\n")
    ps = [proj("VaultDoctor"), proj("DBC", "複数OS/dbc", aliases=["svcscope"]), proj("Other"), proj("Spec")]
    r = devlog.read(str(tmp_path), {"dir": "開発ログ"}, ps)
    vd = r.found[ps[0].key]
    assert len(vd) == 1 and (vd[0].source, vd[0].state, vd[0].value) == ("devlog", None, "2026-10-05")
    assert vd[0].where.endswith("開発ログ/2026-10-05.md#L2")
    assert r.found[ps[1].key][0].value == "2026-10-08"
    assert set(r.found) == {ps[0].key, ps[1].key}      # `##` は見ない・SpecLint の中の Spec は単語でない
    assert "名前を決めた" not in repr(r)


def test_devlog_alias_only_and_japanese_neighbors(tmp_path):
    write(tmp_path / "log" / "2026-10-02.md", "### ゼミ研究(password-manager): 錠の画面\n")
    p = proj("ゼミ研究", "Windows/ゼミ研究", aliases=["password-manager"])
    r = devlog.read(str(tmp_path), {"dir": "log"}, [p])
    assert r.found[p.key][0].value == "2026-10-02"
