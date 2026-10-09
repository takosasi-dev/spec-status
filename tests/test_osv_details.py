# 依存の脆弱性の詳細(osv の details・worst)のテスト: 深刻度の取り方・直る版の選び方・7日の保存・通信が落ちたとき。
from __future__ import annotations

from specstatus import osv
from specstatus.model import ImplPath

from test_guilogic import ps

VULNS = {
    "GHSA-a": {"database_specific": {"severity": "MODERATE"},
               "affected": [{"package": {"ecosystem": "PyPI", "name": "requests"},
                             "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.9"},
                                                                         {"introduced": "2.0"}, {"fixed": "2.20.0"},
                                                                         {"introduced": "3.0"}, {"fixed": "3.1"}]}]}]},
    "GHSA-b": {"database_specific": {"severity": "HIGH"},
               "affected": [{"package": {"ecosystem": "PyPI", "name": "requests"},
                             "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.31.0"}]},
                                        {"type": "GIT", "events": [{"fixed": "abc123"}]}]}]},
    "PYSEC-c": {"severity": [{"type": "CVSS_V3", "score": "9.8"}],
                "affected": [{"package": {"ecosystem": "PyPI", "name": "Py_YAML"},
                              "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "5.4"}]}]}]},
    "OSV-d": {"severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N"}]},
}


def _setup(tmp_path):
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / "requirements.txt").write_text("requests==2.19.0\npy-yaml==5.3\nsix==1.0\nok==1.0\n", encoding="utf-8")
    a = ps("A", "W/A", "実装完了")
    a.folded.impl = [ImplPath(str(impl), "pc", True)]
    ids = {"requests": ["GHSA-a", "GHSA-b"], "py-yaml": ["PYSEC-c"], "six": ["OSV-d"]}

    def post(queries):
        return [{"vulns": [{"id": i} for i in ids.get(q["package"]["name"], [])]} for q in queries]
    return a, post


def test_details(tmp_path):
    a, post = _setup(tmp_path)
    got = []

    def get(vid):
        got.append(vid)
        return VULNS.get(vid, {})
    path = str(tmp_path / "osv.json")
    assert osv.attach([a], {"osv": {"enabled": True}}, now=1000.0, post=post, path=path, get=get) == ""
    assert a.vulns["count"] == 3 and a.vulns["worst"] == "重大"
    assert a.vulns["details"] == [
        {"package": "py-yaml", "version": "5.3", "ids": ["PYSEC-c"], "severity": "重大", "fixed": "5.4"},
        {"package": "requests", "version": "2.19.0", "ids": ["GHSA-a", "GHSA-b"], "severity": "高", "fixed": "2.31.0"},
        {"package": "six", "version": "1.0", "ids": ["OSV-d"], "severity": "不明", "fixed": None},
    ]
    assert (tmp_path / "osv_vulns.json").exists()
    n = len(got)
    osv.attach([a], {"osv": {"enabled": True}}, now=1000.0 + 6 * 86400, post=post, path=path, get=get)
    assert len(got) == n                                                    # 7日以内は聞き直さない

    def down(vid):
        raise OSError("no network")
    a.vulns = None
    note = osv.attach([a], {"osv": {"enabled": True}}, now=1000.0 + 8 * 86400, post=post, path=path, get=down)
    assert "取れません" in note and a.vulns["worst"] == "重大"              # 前の結果を使う


def test_fixed_choice():
    assert osv._fixed_for("2.19.0", ["1.9", "2.20.0", "3.1"]) == "2.20.0"   # 先頭の数字が同じ物を優先
    assert osv._fixed_for("2.19.0", ["1.9", "3.1"]) == "3.1"
    assert osv._fixed_for("2.19.0", ["1.9"]) is None
    assert osv._severity({"database_specific": {"severity": "LOW"}}) == "低"
    assert osv._severity({"severity": [{"score": "5.0"}]}) == "中"


def test_no_get_no_network(tmp_path):
    a, post = _setup(tmp_path)                                              # post を差し替えたら詳細は聞かない
    osv.attach([a], {"osv": {"enabled": True}}, now=1.0, post=post, path=str(tmp_path / "osv.json"))
    assert {d["severity"] for d in a.vulns["details"]} == {"不明"} and a.vulns["worst"] == "不明"
