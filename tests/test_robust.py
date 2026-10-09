# 壊れにくさと速さ(v0.7.0 担当 1): PC 名のかぶり・NFD の名前・出力の差し替えで一時ファイルを残さない・
# git の並列で結果が変わらない・offline で GitHub と OSV.dev に行かない。通信は urlopen を差し替えて止める。
from __future__ import annotations

import os
import threading
import unicodedata
import urllib.request

import pytest

from specstatus import config, core, find, history, osv, snapshots
from specstatus.model import ImplPath

from test_core import DEV, SPEC, make_config, spec_doc, vault, w  # noqa: F401  (vault は fixture)
from test_guilogic import ps


# ---- PC 名のかぶり ----------------------------------------------------------

def test_pc_name_conflicts(tmp_path):
    d = tmp_path / "spec-status" / "data" / "config"
    w(d / "a.toml", '[pc]\nname = "main"\n')
    w(d / "b.toml", '[pc]\nname = " MAIN "\n')         # 前後の空白と大文字小文字の違いもかぶり
    w(d / "c.toml", '[pc]\nname = ""\n')               # 空はかぶりの対象外
    w(d / "d.toml", '[pc]\nname = ""\n')
    w(d / "e.toml", '[pc]\nname = "sub"\n')
    w(d / "f.toml", "[pc\n")                           # 読めない設定は飛ばす
    assert config.pc_name_conflicts(str(tmp_path)) == [
        "PC 名 main が a.toml と b.toml でかぶっています。記録が同期で消えます"]
    assert config.pc_name_conflicts(str(tmp_path / "無い")) == []


def test_load_reports_pc_conflict(vault):
    cfg = make_config(vault)                            # pc.toml の name = "pc"
    assert not any("かぶって" in i for i in core.load(str(vault), cfg).registry_issues)
    w(vault / "spec-status" / "data" / "config" / "other.toml", '[pc]\nname = "pc"\n')
    issues = core.load(str(vault), cfg).registry_issues
    assert "PC 名 pc が other.toml と pc.toml でかぶっています。記録が同期で消えます" in issues


# ---- NFD の名前 -------------------------------------------------------------

def test_nfd_names_keep_real_path(vault, tmp_path):
    name = unicodedata.normalize("NFD", "ガジェット")
    assert name != unicodedata.normalize("NFC", name)
    w(vault / SPEC / "Windows" / name / f"{name}_仕様書.md", spec_doc("ガジェット 仕様書"))   # NTFS は NFC の名前では開けない
    cfg = config.load_config(str(vault), make_config(vault))
    docs, unreadable, _no_spec, _issues = find.find_docs(str(vault), cfg, {})
    doc = next(d for d in docs if d.stem == "ガジェット_仕様書")     # 比べ方と表示は NFC
    assert not unreadable
    assert os.path.isfile(doc.abs_path) and doc.product == "ガジェット" and doc.last_phase == 3
    assert doc.path == f"{SPEC}/Windows/ガジェット/ガジェット_仕様書.md"

    s = ps("ガジェット", "Windows/ガジェット")
    s.project.docs = [doc]
    folder = str(tmp_path / "snap")
    snapshots.save(s, folder)
    assert snapshots.diff(s, folder) == []              # 実際のパスで読めて、写しと同じ
    nfc_doc = type(doc)(**{**doc.__dict__, "abs_path": unicodedata.normalize("NFC", doc.abs_path)})
    assert snapshots._file(doc, folder) == snapshots._file(nfc_doc, folder)   # 写しの名前は前(NFC)と同じ


# ---- 出力の差し替え ---------------------------------------------------------

def test_replace_leaves_no_temp(tmp_path, monkeypatch):
    out = tmp_path / "00_実装状況.md"
    core._replace(str(out), "一\n")
    core._replace(str(out), "二\n")
    assert out.read_text(encoding="utf-8") == "二\n" and os.listdir(tmp_path) == [out.name]

    def locked(src, dst):
        raise PermissionError("使用中")
    monkeypatch.setattr(core.os, "replace", locked)
    monkeypatch.setattr(core, "REPLACE_WAIT_S", 0)
    with pytest.raises(PermissionError):
        core._replace(str(out), "三\n")
    assert out.read_text(encoding="utf-8") == "二\n" and os.listdir(tmp_path) == [out.name]


# ---- git の並列 -------------------------------------------------------------

def test_git_dates_parallel_same_result():
    git = {"C:/a": "2026-10-01", "C:/b": None, "C:/c": "2026-09-01"}
    gate = threading.Barrier(2, timeout=5)             # 並列でなければ2本目が来ずに止まる
    asked = []

    def fake_git(path):
        asked.append(path)
        if path in ("C:/a", "C:/b"):
            gate.wait()
        return git[path]
    assert history.git_dates(["C:/a", "C:/b", "C:/a", "C:/c"], fake_git) == git
    assert sorted(asked) == ["C:/a", "C:/b", "C:/c"]    # 同じフォルダは1回
    assert history.git_dates([], fake_git) == {}


def test_mark_stale_same_as_sequential():
    from datetime import date
    git = {f"C:/impl/{i}": f"2026-0{1 + i % 9}-15" for i in range(20)}
    rows = []
    for i in range(20):
        s = ps(f"p{i}", f"W/p{i}", "着手済")
        s.folded.impl = [ImplPath(f"C:/impl/{i}", "pc", True), ImplPath(f"C:/impl/{(i + 1) % 20}", "pc", True)]
        rows.append(s)
    history.mark_stale(rows, date(2026, 10, 9), 30, git.get)
    for i, s in enumerate(rows):
        expect = max(git[f"C:/impl/{i}"], git[f"C:/impl/{(i + 1) % 20}"])
        assert s.last_activity == expect


# ---- offline ----------------------------------------------------------------

def test_osv_offline_uses_cache_only(tmp_path):
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / "requirements.txt").write_text("requests==2.19.0\n", encoding="utf-8")
    a = ps("A", "W/A", "実装完了")
    a.folded.impl = [ImplPath(str(impl), "pc", True)]
    cfg = {"osv": {"enabled": True}}
    path = str(tmp_path / "osv.json")
    osv.attach([a], cfg, now=1000.0, post=lambda q: [{"vulns": [{"id": "GHSA-x"}]}], path=path,
               get=lambda vid: {})

    def boom(*_a):
        raise AssertionError("offline なのに聞いた")
    a.vulns = None
    assert osv.attach([a], cfg, now=1e9, post=boom, path=path, get=boom, offline=True) == ""
    assert a.vulns["count"] == 1 and a.vulns["ids"] == ["GHSA-x"]


def test_load_offline_never_fetches(vault, tmp_path, monkeypatch):
    impl = tmp_path / "impl" / "Alpha"
    impl.mkdir(parents=True)
    (impl / "NOTES.md").write_text("x", encoding="utf-8")
    (impl / "requirements.txt").write_text("requests==2.19.0\n", encoding="utf-8")
    cfg = make_config(vault, implroots=[str(tmp_path / "impl")])
    with open(cfg, "a", encoding="utf-8") as f:
        f.write('[github]\nowner = "someone"\n[osv]\nenabled = true\n')
    calls = []

    def no_net(*a, **kw):
        calls.append(a)
        raise OSError("通信は止めてある")
    monkeypatch.setattr(urllib.request, "urlopen", no_net)
    core.load(str(vault), cfg, offline=True)
    code, _msg, _board = core.build(str(vault), cfg, offline=True)
    assert code == 0 and calls == []
    core.load(str(vault), cfg)                          # offline でなければ聞きに行く(差し替えが効いている確かめ)
    assert calls
