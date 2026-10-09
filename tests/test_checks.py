# 仕様書の書き換え(history.mark_spec_changed)・受け入れ基準のチェック(find.ac_count)・依存の脆弱性(osv)・GitHub の保存の形。
# ネットワークには繋がない(問い合わせる関数を差し替える)。
from __future__ import annotations

import json
from datetime import datetime

from specstatus import find, github, osv, render
from specstatus.model import ImplPath

from test_guilogic import ps, rec


def test_ac_count():
    body = ["## 受け入れ基準", "- [ ] AC-1: 開く", "- [x] AC-2: 閉じる", "  - [X] **AC-3**: 太字", "- [ ] 普通の ToDo",
            "* [x] AC-10 星印", "- [x] ACME は数えない"]
    assert find.ac_count(body) == (3, 4)
    assert find.ac_count(["- [ ] やること"]) is None


def test_ac_on_status_sums_spec_docs():
    p = ps("A", "W/A")
    p.project.docs[0].ac = (2, 5)
    assert p.ac == (2, 5) and render.ac_text(p) == "2/5"
    assert ps("B", "W/B").ac is None and render.ac_text(ps("B", "W/B")) == ""


def test_spec_changed():
    at = "2026-10-05T10:00:00+09:00"
    t = datetime.fromisoformat(at).timestamp()
    done = ps("done", "W/done", "実装完了", history=[rec(at)])
    soon = ps("soon", "W/soon", "実装完了", history=[rec(at)])
    doing = ps("doing", "W/doing", "着手済", history=[rec(at)])
    norec = ps("norec", "W/norec", "実装完了")
    times = {"C:/v/done_仕様書.md": t + 86400 * 2, "C:/v/soon_仕様書.md": t + 30,
             "C:/v/doing_仕様書.md": t + 86400, "C:/v/norec_仕様書.md": t + 86400}
    from specstatus import history
    history.mark_spec_changed([done, soon, doing, norec], times.__getitem__)
    assert done.spec_changed == "2026-10-07"
    assert soon.spec_changed is None            # 記録と同じ作業(60 秒以内)の書き換えは数えない
    assert doing.spec_changed is None and norec.spec_changed is None


def test_osv_parse(tmp_path):
    lock = {"lockfileVersion": 3, "packages": {"": {"name": "app"}, "node_modules/lodash": {"version": "4.17.20"},
                                                  "node_modules/a/node_modules/@scope/b": {"version": "1.0.0"},
                                                  "node_modules/local": {"link": True}}}
    (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests==2.19.0  # 古い\nflask>=2\nPyYAML[c] == 5.3 ; python_version<'4'\n",
                                               encoding="utf-8")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "requirements.txt").write_text("x==1\n", encoding="utf-8")          # 3段下は見ない
    (tmp_path / "node_modules" / "z").mkdir(parents=True)
    (tmp_path / "node_modules" / "z" / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "Cargo.lock").write_text('[[package]]\nname = "serde"\nversion = "1.0.0"\n', encoding="utf-8")
    files = osv.find_lockfiles(str(tmp_path))
    assert [f.replace("\\", "/").split(tmp_path.name + "/")[1] for f in files] == [
        "package-lock.json", "requirements.txt", "sub/Cargo.lock"]
    assert osv.parse(files[0]) == [("npm", "lodash", "4.17.20"), ("npm", "@scope/b", "1.0.0")]
    assert osv.parse(files[1]) == [("PyPI", "requests", "2.19.0"), ("PyPI", "PyYAML", "5.3")]
    assert osv.parse(files[2]) == [("crates.io", "serde", "1.0.0")]


def test_osv_attach(tmp_path):
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / "requirements.txt").write_text("requests==2.19.0\nsix==1.16.0\n", encoding="utf-8")
    a = ps("A", "W/A", "実装完了")
    a.folded.impl = [ImplPath(str(impl), "pc", True)]
    b = ps("B", "W/B", "実装完了")
    sent = []

    def post(queries):
        sent.append(queries)
        return [{"vulns": [{"id": "GHSA-x"}, {"id": "CVE-1"}]} if q["package"]["name"] == "requests" else {}
                for q in queries]
    cfg = {"osv": {"enabled": True}}
    path = str(tmp_path / "osv.json")
    assert osv.attach([a, b], cfg, now=1000.0, post=post, path=path) == ""
    assert a.vulns["count"] == 1 and a.vulns["total"] == 2 and a.vulns["ids"] == ["CVE-1", "GHSA-x"]
    assert a.vulns["packages"] == ["requests@2.19.0(CVE-1, GHSA-x)"] and b.vulns is None
    assert len(sent[0]) == 2
    osv.attach([a], cfg, now=2000.0, post=post, path=path)          # 1日以内は聞き直さない
    assert len(sent) == 1

    def down(queries):
        raise OSError("no network")
    a.vulns = None
    assert "繋がりません" in osv.attach([a], cfg, now=1e9, post=down, path=path)
    assert a.vulns["count"] == 1                                       # 前の結果を使う
    assert osv.attach([a], {}, post=down) == ""                       # 設定でオフなら何もしない


def test_github_cache_version(tmp_path):
    path = tmp_path / "g.json"
    path.write_text(json.dumps({"https://x": {"etag": "e", "fetched": 1, "data": []}}), encoding="utf-8")   # 古い形
    assert github._load(str(path)) == {}
    github._save(str(path), {"u": {"etag": "", "fetched": 1, "data": None}})
    assert github._load(str(path)) == {"u": {"etag": "", "fetched": 1, "data": None}}
